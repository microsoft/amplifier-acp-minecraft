"""Optional explicit idle maintenance. Never scheduled automatically by the game.

Candidate Instance contract; enable only through advertised capability + command.
Owner receipts are an audit, not a retry queue. No task or lease endpoint is called.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
from harness_capabilities import maintenance, MAINTENANCE_META


def closed_body(state):
    if not isinstance(state,dict):return False
    lease=state.get('action_lease')
    return (state.get('ready') is True and state.get('busy') is False
            and state.get('turn_active') is False and isinstance(lease,dict)
            and lease.get('version')==1 and lease.get('lease_id') is None
            and lease.get('renewable') is False)


async def compact(client, home, operation_id, status, *, timeout=600):
    """Explicit caller supplies a fresh authenticated body status reader.

    The caller must own the controller's idle boundary. The Instance additionally
    excludes competing session input. No unknown operation is auto-repeated.
    """
    if not maintenance(client.info) or 'compact' not in client.available_commands.get(client.session,set()):
        raise ValueError('Maintenance route and session compact command must both be advertised')
    if (not isinstance(operation_id,str) or not 1<=len(operation_id.encode())<=128
            or type(timeout) not in (int,float) or not 0<timeout<=3600):
        raise ValueError('Use a stable bounded operation ID and maintenance wait')
    if not client.session or client.active_prompt_id is not None or client.replaying or client.maintenance_active:
        raise ValueError('Session is not idle')
    client.maintenance_active=True
    path=None;receipt=None;successful=False
    try:
        if not closed_body(await status()) or client.permission_active():
            raise ValueError('Close game action authority and settle body operations before maintenance')
        directory=Path(home)/'maintenance-receipts';directory.mkdir(mode=0o700,parents=True,exist_ok=True)
        path=directory/(hashlib.sha256(operation_id.encode()).hexdigest()+'.json')
        receipt={'version':1,'operation':'compact','operationId':operation_id,'sessionId':client.session,
                 'status':'unknown','reason':'submitted','prompt_terminal':False,'completion':'not_established'}
        # Exclusive, durable before wire send. Existing/corrupt/unknown receipts
        # all require inspection; none can silently become a retry.
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream:
            json.dump(receipt,stream);stream.flush();os.fsync(stream.fileno())
        compaction_id=None;compaction_status='unknown'
        async def update(item):
            nonlocal compaction_id,compaction_status
            if item.get('sessionUpdate')!='compaction_update':return
            identity,state=item.get('compactionId'),item.get('status')
            if not isinstance(identity,str) or not identity:return
            if compaction_id is None and state=='in_progress':compaction_id=identity
            if identity==compaction_id and state in ('in_progress','completed','failed','cancelled'):
                compaction_status=state
                client.observe('maintenance_compaction',status=state,prompt_settled=False)
        try:
            result=await asyncio.wait_for(client.request('session/prompt',{
                'sessionId':client.session,'prompt':[{'type':'text','text':'/compact'}],
                '_meta':{MAINTENANCE_META:{'version':1,'operation':'compact','operationId':operation_id}}
            },update),timeout)
            receipt['prompt_terminal']=True
            remote=result.get('_meta',{}).get(MAINTENANCE_META,{})
            matches=(isinstance(remote,dict) and remote.get('version')==1 and remote.get('operation')=='compact'
                     and remote.get('operationId')==operation_id and remote.get('sessionId')==client.session
                     and remote.get('compactionId')==compaction_id)
            successful=(matches and remote.get('status')=='completed' and compaction_id is not None
                        and compaction_status=='completed' and result.get('stopReason')=='end_turn')
            receipt.update(status='completed' if successful else 'cancelled' if result.get('stopReason')=='cancelled'
                           else 'failed' if compaction_status=='failed' else 'unknown',
                           reason='matching_compaction_and_terminal' if successful else 'not_verified',
                           compactionId=compaction_id,compaction_status=compaction_status)
            # This read does not grant/resume work; callers still recheck their
            # original assignment deadline, limits and pending human input.
            receipt['body_still_idle']=closed_body(await status())
        except (Exception,asyncio.CancelledError) as error:
            successful=False
            receipt.update(status='unknown',reason=type(error).__name__)
            if isinstance(error,(asyncio.TimeoutError,asyncio.CancelledError)):
                try:await client.cancel()
                except Exception:pass
            raise
        finally:
            try:
                if not successful:await client.close()
            finally:
                temporary=path.with_suffix('.tmp')
                with open(temporary,'w',opener=lambda p,flags:os.open(p,flags,0o600)) as stream:
                    json.dump(receipt,stream);stream.flush();os.fsync(stream.fileno())
                temporary.replace(path)
        return receipt
    finally:
        client.maintenance_active=False
