"""One independent ACP endpoint + one Minecraft body. No fleet or model SDK."""
from task_bounds import allowance_remaining
import argparse
import asyncio
import hashlib
import json
import math
import os
import re
from pathlib import Path
import time
import urllib.request
from conversation_awareness import Awareness
from planner_prompt import planner_prompt
from prompt_lifecycle import await_terminal
from sequence_settlement import settle_sequence
from acp_client import Client, turn_disposition, GAME_TOOLS, REPLY_TOOLS
from attention import Attention, fingerprint
from assessment import Assessment, POLICY, signature
from watches import Watches
from conversation_attention import ConversationAttention


def minecraft_reply_lines(text, limit=8, width=230):
    """Fit the Java chat/body UTF-16 limit; make any bounded shortening visible."""
    def prefix(value, available):
        used=0
        for i, char in enumerate(value):
            used+=2 if ord(char)>0xffff else 1
            if used>available:return value[:i]
        return value
    remaining=' '.join(text.split());lines=[]
    while remaining and len(lines)<limit:
        part=prefix(remaining,width)
        if len(part)<len(remaining):
            # Surface packetization of an already settled answer, never an ACP
            # message-completion heuristic. Fall back to words for long sentences.
            endings=list(re.finditer(r'[.!?…][\"\'”’)]*(?=\s|$)',part))
            if endings:part=part[:endings[-1].end()]
            elif ' ' in part:part=part.rsplit(' ',1)[0]
        lines.append(part)
        remaining=remaining[len(part):].lstrip()
    truncated=bool(remaining)
    if truncated:
        suffix=' [Message shortened.]'
        lines[-1]=prefix(lines[-1],width-len(suffix)).rstrip()+suffix
    return lines,truncated


async def deliver_final_reply(text, revision, request, observe, *, sleep=asyncio.sleep):
    lines,truncated=minecraft_reply_lines(text)
    sent=0
    for line in lines:
        if sent:await sleep(.8)
        delivery=await request('/reply',{'text':line,'conversation_revision':revision})
        if delivery.get('sent') is False:
            observe('final_reply_withheld',reason='public_context_changed_before_delivery',sent_chunks=sent)
            break
        sent+=1
    observe('final_reply_delivery',sent_chunks=sent,planned_chunks=len(lines),
            shortened=truncated,all_chunks_sent=sent==len(lines))


def control(cfg, path, payload=None):
    req = urllib.request.Request(f"http://127.0.0.1:{cfg['control_port']}{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Authorization': 'Bearer '+cfg['token'], 'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=70) as response:
        return json.load(response)


def save(path, value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2));os.chmod(tmp,0o600);tmp.replace(path)


CAPACITY_NOTICE_INTERVAL = 15 * 60


def load_capacity_notice(path):
    """Only a notification timestamp; never a task, queue, or capacity grant."""
    try:
        value=json.loads(path.read_text()).get('last_attempt_at')
        if type(value) in (int,float) and math.isfinite(value) and value>=0:
            return {'last_notice_at':value}
    except (OSError,ValueError,AttributeError):
        pass
    return {}


async def capacity_gate(calls,state,request,observe,waiting,*,now=None,sleep=asyncio.sleep,while_waiting=None,notice_path=None):
    """Rate limits wait before consuming messages; never cancel or renew a task."""
    now=time.time() if now is None else now
    calls[:]=[t for t in calls if t>now-3600]
    if len(calls)<30:
        if waiting.get('active'):observe('budget_resumed')
        # One freed slot may refill immediately. Keep notice cadence across those
        # short resumptions, independently of the actual capacity-wait telemetry.
        waiting.pop('active',None);waiting.pop('notified',None)
        return True
    delay=max(.05,min(calls)+3600-now)
    if not waiting.get('active'):
        observe('budget_wait',resume_after_seconds=delay)
        waiting['active']=True
    has_work=state.get('pending_messages',0)>0 or (state.get('task') or {}).get('status') in ('running','waiting')
    if has_work and not waiting.get('notified'):
        last=waiting.get('last_notice_at')
        if last is not None and last>now:
            # A wall-clock correction must not suppress notices indefinitely.
            waiting['last_notice_at']=last=now
            if notice_path is not None:save(notice_path,{'last_attempt_at':now})
        waiting['notified']=True
        if last is None or now-last>=CAPACITY_NOTICE_INTERVAL:
            waiting['last_notice_at']=now
            # Persist before sending: a lost reply or restart must not replay a
            # notice which may already have appeared in the public conversation.
            if notice_path is not None:save(notice_path,{'last_attempt_at':now})
            await request('/notice',{'kind':'budget'})
        else:
            observe('budget_notice_suppressed',reason='recent_capacity_notice',
                    retry_after_seconds=CAPACITY_NOTICE_INTERVAL-(now-last))
    if while_waiting:
        await while_waiting()
    await sleep(min(10,delay))
    return False


async def human_reply_messages(request,connect,attention):
    """Human-only input lane; source/ticket integrity survives unmetered replies."""
    def available(admission):
        return admission.get('version')==1 and (admission.get('unmetered') is True or (admission.get('remaining') or 0)>0)
    def select(messages,admission):
        eligible=set(admission.get('eligible_ids',[]))
        selected=[m for m in messages if m.get('id') in eligible and m.get('source')=='human']
        # A ticket binding peers cannot be split or promoted into this reserve.
        selected=[m for m in selected if not m.get('attention_offer') or not any(
            peer.get('source')!='human' and peer.get('attention_offer')==m['attention_offer'] for peer in messages)]
        if not selected:return []
        offer=selected[0].get('attention_offer')
        audience=selected[0].get('username') if selected[0].get('whisper') else None
        return [m for m in selected if m.get('attention_offer')==offer and
                (m.get('username') if m.get('whisper') else None)==audience][:8]

    admission=await request('/conversation/admission')
    if not available(admission):return []
    selected=select(await request('/inbox/peek'),admission)
    if not selected and attention and await request('/participation?human_only=1'):
        client=await connect()
        await attention.consider(request,client,human_only=True)
        admission=await request('/conversation/admission')
        if not available(admission):return []
        selected=select(await request('/inbox/peek'),admission)
    return selected


async def run(home):
    cfg=json.loads((home/'config.json').read_text())
    endpoint=json.loads((home/'endpoint.json').read_text())
    endpoint['mcp_servers']=[{'type':'http','name':'minecraft','url':cfg.get('mcp_url',f"http://127.0.0.1:{cfg['control_port']}/mcp"),
        'headers':[{'name':'Authorization','value':'Bearer '+cfg['token']}]}]
    if cfg.get('context_provider_id'):
        endpoint['session_meta']={'io.github.bkrabach.conversation':{'provider_id':cfg['context_provider_id'],'grant':cfg['context_grant']}}
    identity=hashlib.sha256(json.dumps(endpoint,sort_keys=True).encode()).hexdigest()
    def observe(kind,**data):
        print(json.dumps({'time':time.time(),'kind':kind,**data}),flush=True)
    incoming_chat_only=cfg.get('incoming_chat_only') is True
    intake_enabled=(cfg.get('human_task_intake') or {}).get('enabled') is True
    assessment_enabled=(not incoming_chat_only or intake_enabled) and (cfg.get('decision_attention') or {}).get('policy')==POLICY
    attention=(Assessment if assessment_enabled else Attention)(home,cfg.get('decision_attention'),observe)
    state_signature=signature if assessment_enabled else fingerprint
    client=None
    calls_path=home/'calls.json'
    calls=json.loads(calls_path.read_text()) if calls_path.exists() else []
    reply_calls_path=home/'reply-calls.json'
    reply_calls=json.loads(reply_calls_path.read_text()) if reply_calls_path.exists() else []
    notice_path=home/'capacity-notice.json'
    budget_waiting=load_capacity_notice(notice_path)
    activity_attention=ConversationAttention(observe) if (cfg.get('human_engagement') or {}).get('activity_scope')=='conversation_only' else None
    connection_failures=0
    last_continuation=None
    async def request(path,payload=None):
        return await asyncio.to_thread(control,cfg,path,payload)
    watches=Watches(home,cfg['decision_attention'],request,observe) if cfg.get('agent_watches') and (not incoming_chat_only or intake_enabled) else None
    conversation_attention=ConversationAttention(observe) if (cfg.get('conversation_attention') or {}).get('enabled') else None
    async def connect():
        nonlocal client, connection_failures
        # Both attention and prompt delivery can follow an idle endpoint restart.
        # Reload before either request, and before reserving any work or inbox.
        # A disconnect after a prompt starts remains interrupted; never replay it.
        if client is not None and client.transport_closed():
            observe('connection_closed_before_turn',session_id=client.session)
            await client.close();client=None
        if client is not None:return client
        client=Client(endpoint,observe);await client.start()
        client.permission_active=lambda: control(cfg,'/status').get('turn_active',False)
        def permission_tools():
            status=control(cfg,'/status')
            if status.get('conversation_only'):
                return REPLY_TOOLS | ({'task_accept','task_amend','task_accept_help'} if status.get('task_intake_enabled') and not status.get('ambient_activity') else set())
            return GAME_TOOLS
        client.permission_tools=permission_tools
        if not client.info.get('agentCapabilities',{}).get('mcpCapabilities',{}).get('http'):
            raise RuntimeError('This adapter requires an ACP endpoint supporting HTTP MCP')
        previous=None
        if (home/'session.json').exists():
            stored=json.loads((home/'session.json').read_text())
            if stored.get('binding')==identity:previous=stored.get('session')
        await client.open_session(previous)
        save(home/'session.json',{'binding':identity,'session':client.session})
        connection_failures=0
        return client

    async def observe_attention(state):
        watch_managed=False
        notifications=[]
        if watches:
            await watches.poll()
            notifications=await watches.pending()
            watch_managed=await watches.managed()
        if notifications and (state.get('task') or {}).get('status')=='waiting':
            await request('/wake',{'task_id':state['task']['id'],'generation':state['generation']})
            observe('watch_applied',application='wake',ids=[n['id'] for n in notifications])
            state=await request('/state')
        elif not watch_managed and await attention.consider(state):
            fresh=await request('/state')
            if state_signature(fresh)==state_signature(state) and fresh.get('generation')==state.get('generation'):
                await request('/wake',{'task_id':state['task']['id'],'generation':state['generation']})
                observe('assessment_applied',application='wake',task_id=state['task']['id'],fingerprint=state_signature(state))
                state=await request('/state')
            else:
                observe('assessment_discarded',reason='observation_changed_before_wake',fingerprint=state_signature(state))
        return state

    async def observe_capacity_wait():
        # Planner capacity does not suspend bounded attention. A delivery may
        # satisfy an authored watch before it expires, even while no ACP turn
        # can start. Waking marks existing work ready; capacity still blocks it.
        fresh=await request('/state')
        task=fresh.get('task') or {}
        if (not fresh.get('busy') and not fresh.get('turn_active')
            and task.get('status')=='waiting' and allowance_remaining(task)):
            await observe_attention(fresh)

    # A controller restart must not replay an uncertain in-flight task.
    while True:
        turn_started=False
        try:
            await request('/recover',{});break
        except Exception:
            await asyncio.sleep(2)
    while True:
        turn_started=False
        try:
            state=await request('/state')
            if not state.get('ready'):
                await asyncio.sleep(2);continue
            # Leave queued messages in the body. Stop clears them immediately;
            # state is reread after each wait so deadlines still expire normally.
            work_allowed=state.get('task_capabilities',{}).get('autonomous_work_allowed',not incoming_chat_only)
            if work_allowed and not state.get('turn_active') and not state.get('busy'):
                continuation=await request('/continuation',{'generation':state.get('generation')})
                continuation_key=(state.get('task',{}).get('id') if state.get('task') else None,json.dumps(continuation,sort_keys=True))
                if continuation.get('action') not in ('hold','continue') and continuation_key!=last_continuation:
                    observe('continuation_policy',**continuation)
                last_continuation=continuation_key
                state=await request('/state')
            calls[:]=[t for t in calls if t>time.time()-3600]
            conversation_only=False
            messages=[]
            if intake_enabled or not work_allowed or len(calls)>=30:
                messages=await human_reply_messages(request,connect,conversation_attention)
                conversation_only=bool(messages)
            if not messages and activity_attention:
                if await request('/activity/participation'):
                    await activity_attention.consider(request,await connect(),activity=True)
                admission=await request('/conversation/admission')
                eligible=set(admission.get('eligible_ids',[]))
                messages=[m for m in await request('/inbox/peek') if m.get('source')=='activity' and m.get('id') in eligible][:1]
                conversation_only=bool(messages)
            if not messages and (cfg.get('human_task_intake',{}).get('delegation') or {}).get('enabled') is True:
                # Peer proposals remain ambient, never the unmetered human lane.
                if conversation_attention and await request('/participation'):
                    await conversation_attention.consider(request,await connect())
                admission=await request('/conversation/admission')
                eligible=set(admission.get('eligible_ids',[]))
                messages=[m for m in await request('/inbox/peek') if m.get('source')=='agent' and m.get('id') in eligible][:1]
                conversation_only=bool(messages)
            if not work_allowed and not conversation_only:
                await asyncio.sleep(2);continue
            if not conversation_only:
                # Explicit installation policy removes connector pacing, not
                # task authority or host/provider limits. Calls remain counted.
                if (cfg.get('human_engagement') or {}).get('enabled') is not True:
                    if not await capacity_gate(calls,state,request,observe,budget_waiting,while_waiting=observe_capacity_wait,notice_path=notice_path):continue
                messages=await request('/inbox/peek')
            if not messages and conversation_attention and await request('/participation'):
                await connect()
                await conversation_attention.consider(request,client)
                messages=await request('/inbox/peek')
            if not messages:
                state=await observe_attention(state)
                if (state.get('task') or {}).get('status')!='running':
                    await asyncio.sleep(1);continue
                messages=[{'source':'continuation','message':'Continue the accepted game task. Inspect current world state and progress before acting.'}]
                await asyncio.sleep(0 if (cfg.get('human_engagement') or {}).get('enabled') is True else 3)
                newer=await request('/inbox/peek')
                if newer:messages=newer
            await connect()
            offers=[m['attention_offer'] for m in messages if m.get('attention_offer')]
            attention_offer=offers[0] if offers else None
            if offers and any(offer!=attention_offer for offer in offers):
                raise RuntimeError('Mixed attention offers cannot share a turn')
            await request('/turn',{'renewable_lease':not conversation_only,'conversation_only':conversation_only,'expected_generation':state.get('generation'),'continuation':all(m.get('source')=='continuation' for m in messages),'peer_only':all(m.get('source')=='agent' for m in messages),'message_ids':[m['id'] for m in messages if m.get('id')]})
            turn_started=True
            state=await request('/state')  # The new turn resets action/time budgets.
            watch_notifications=[]
            if watches and not conversation_only:
                await watches.poll()
                watch_notifications=await watches.pending()
            assessment=None
            if assessment_enabled and not conversation_only:
                assessment=await attention.before_turn(state)
                fresh=await request('/state')
                if not fresh.get('turn_active') or fresh.get('generation')!=state.get('generation'):
                    raise RuntimeError('Turn stopped during assessment')
                if assessment and state_signature(fresh)!=assessment['fingerprint']:
                    observe('assessment_discarded',reason='observation_changed',fingerprint=assessment['fingerprint'])
                    assessment=None
                state=fresh
                if assessment:
                    observe('assessment_applied',application='advisory',task_id=state['task']['id'],fingerprint=assessment['fingerprint'])
            if watch_notifications:
                observe('watch_applied',application='advisory',ids=[n['id'] for n in watch_notifications])
            world=await request('/observation')
            if not world.get('turn_active') or world.get('generation')!=state.get('generation'):
                raise RuntimeError('Turn stopped before planner observation')
            observe('turn_started',messages=messages,conversation_only=conversation_only)
            prompt=planner_prompt(messages,world,assessment,watch_notifications)
            if conversation_only:
                reply_calls[:]=[t for t in reply_calls if t>time.time()-3600]
                reply_calls.append(time.time());save(reply_calls_path,reply_calls)
            else:
                calls.append(time.time());save(calls_path,calls)
            awareness=Awareness(home,client,world.get('conversation',{}),observe)
            operator_awareness=None
            try:
                operator_awareness=Awareness(home,client,await request('/operator-inputs'),observe,audience='operator')
            except Exception as error:
                observe('operator_awareness_unavailable',category=type(error).__name__,fallback='queued_input')
            pending=asyncio.create_task(client.prompt(prompt,attention_offer=attention_offer))
            last_renewed=time.monotonic()
            try:
                while not pending.done():
                    await asyncio.wait({pending},timeout=1)
                    if not pending.done():
                        status=await request('/status')
                        if not status.get('turn_active'):
                            await client.cancel()
                            # Authority has already closed. Cancellation is not
                            # settlement: observe a bounded terminal reply, never replay.
                            observe('planner_cancel_settlement',**(await await_terminal(pending)))
                            if not pending.done():pending.cancel()
                            await client.close();client=None
                            raise RuntimeError('Action authority ended; inspect effects before continuing')
                        lease=status.get('action_lease') or {}
                        if lease.get('version')!=1:
                            raise RuntimeError('Body lacks action lease protocol; update paired adapter/body at idle')
                        if lease.get('renewable') and time.monotonic()-last_renewed>=30:
                            await request('/turn/renew',{'lease_id':lease['lease_id'],'task_id':lease['task_id']})
                            last_renewed=time.monotonic()
                        if client.lifecycle:client.lifecycle.sample()
                        try:
                            await awareness.consider(await request('/conversation'))
                            if operator_awareness:
                                await operator_awareness.consider(await request('/operator-inputs'))
                        except Exception as error:
                            observe('awareness_source_unavailable',category=type(error).__name__)
                result=await pending
                await awareness.finish()
                if operator_awareness:
                    await operator_awareness.finish()
            finally:
                if not pending.done():pending.cancel()
            operation=await settle_sequence(request,result,observe)
            if operation['waited']:
                # The model ended before seeing final physical results. Preserve
                # those receipts, but do not publish an unsupported completion claim.
                result['final_text']=''
                observe('final_reply_withheld',reason='background_operation_settled_after_prompt')
            disposition=turn_disposition(result,(await request('/status')).get('busy',False))
            # If the human stopped the work, do not post a late final response.
            text=result.get('final_text',result['text']).strip()
            if disposition=='complete' and text:
                fresh=await request('/conversation')
                revision=awareness.final_revision(fresh)
                if revision is None:
                    observe('final_reply_withheld',reason='public_context_not_exposed_or_incorporated')
                else:
                    await deliver_final_reply(text,revision,request,observe)
            observe('turn_completed',stop_reason=result['stop_reason'],disposition=disposition,
                    unsettled_tool_count=len(result.get('unsettled_tools',[])))
            if watches and not conversation_only and disposition=='complete':
                await watches.acknowledge(watch_notifications)
            await request('/finish',{'error':disposition=='interrupted','budget_limited':disposition=='limited'})
        except asyncio.CancelledError:
            if client:await client.close()
            raise
        except Exception as e:
            if turn_started:
                try:await request('/finish',{'error':True})
                except Exception:pass
            observe('adapter_error',error=str(e),error_type=type(e).__name__,phase='turn' if turn_started else 'connection_or_scheduling')
            if client:
                await client.close();client=None
            try:
                status=await request('/status')
                if turn_started and (status.get('turn_active') or (status.get('task') or {}).get('status')=='needs_review'):
                    await request('/notice',{'kind':'paused'})
            except Exception:pass
            if client:await client.close();client=None
            if not turn_started:
                connection_failures+=1
                delay=min(60,5*2**min(connection_failures-1,4))
                observe('connection_retry_wait',seconds=delay,queued_messages_preserved=True)
                await asyncio.sleep(delay)
            else:await asyncio.sleep(3)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);a=p.parse_args()
    asyncio.run(run(a.home.expanduser()))
