"""Minecraft policy/collection around the official ACP Python SDK.

The SDK owns protocol models, framing, request IDs, correlation and callbacks.
This wrapper owns process lifetime, game permissions and bounded observations.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import signal
from prompt_lifecycle import PromptLifecycle
from acp import connect_to_agent
from acp.connection import StreamDirection
from acp.exceptions import RequestError
from pydantic import ValidationError
from acp.schema import (InitializeRequest, NewSessionRequest, LoadSessionRequest,
                        PromptRequest, SessionNotification, RequestPermissionResponse)
from acp.utils import model_to_kwargs


def wire(model):
    return model.model_dump(mode='json', by_alias=True, exclude_none=True, exclude_unset=True)


class _Callbacks:
    def __init__(self, owner):
        self.owner = owner

    async def session_update(self, session_id, update, **kwargs):
        # The public SDK observer queues typed updates in receive order, before
        # the SDK's independent callback tasks can overtake one another.
        # Do this synchronously in the SDK callback, before its next permission
        # callback. The raw observer may already have seen later wire frames;
        # those must not retroactively authorize an earlier permission request.
        item = wire(update)
        if item.get('sessionUpdate') in ('tool_call', 'tool_call_update'):
            tid = item['toolCallId']
            self.owner.tool_calls[tid] = {**self.owner.tool_calls.get(tid, {}), **item}

    async def request_permission(self, session_id, tool_call, options, **kwargs):
        return self.owner._permission(session_id, wire(tool_call), [wire(o) for o in options])

__version__ = "0.1.0"

# One source for both callback enforcement and the agent-visible policy.
GAME_TOOLS = frozenset({'observe','survey','inspect','find','chat','tell','task_capabilities','move','follow','cancel_movement','action_sequence','cancel_sequence','start_sequence','sequence_status','gather','craft','place','build','give','stop','work_begin','work_report','work_reopen','map','plan_route','dig','set_open','activate_control','tell','work_note','inventory','entities','shear','furnace','container','attention_watch','attention_watches','attention_cancel','read_sign','write_sign','screenshot','screenshots','screenshot_read','conversation','till','task_accept','task_amend','task_accept_help','work_resume','resume_activity'})


REPLY_TOOLS = frozenset({'observe','conversation','entities','inventory','inspect','read_sign','survey','map','plan_route','find','chat','tell','task_capabilities','sequence_status','resume_activity'})


class ProtocolError(RuntimeError):
    pass


def turn_disposition(result, body_busy=False):
    """A clean protocol budget boundary is resumable, an unfinished action isn't."""
    if body_busy or result.get('unsettled_tools'):
        return 'interrupted'
    if result.get('stop_reason') == 'end_turn':
        return 'complete'
    if result.get('stop_reason') in ('max_tokens','max_turn_requests'):
        return 'limited'
    return 'interrupted'


class Client:
    def __init__(self, endpoint, observe, *, load_timeout=180, idle_timeout=30):
        self.endpoint, self.observe = endpoint, observe
        self.process = None
        self.requests_sent = 0
        self.session = None
        self.info = None
        self.connection = None
        self.tool_calls = {}
        self.permission_active = lambda: False
        self.permission_tools = lambda: GAME_TOOLS
        self.load_timeout, self.idle_timeout = load_timeout, idle_timeout
        self.replaying = False
        self.update_queue = asyncio.Queue(maxsize=1024)
        self.update_worker = None
        self.update_handler = None
        self.foreground = False
        self.failed = None
        self.fatal = None
        self.activity_at = 0
        self.frames = self.observed_bytes = 0
        self.active_prompt_id = None
        self.lifecycle = None
        self.available_commands = {}
        self.maintenance_active = False

    def transport_closed(self):
        """Known local closure only; this makes no ACP request or health promise."""
        return (self.process is None or self.failed is not None or self.process.returncode is not None
                or self.process.stdin.is_closing() or self.process.stdout.at_eof())

    async def start(self):
        # Explicit inheritance avoids carrying unrelated access tokens to agents.
        names = ("PATH", "HOME", "USER", "LANG", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "SSL_CERT_FILE", "SSL_CERT_DIR", "SSH_AUTH_SOCK")
        env = {name: os.environ[name] for name in names if name in os.environ}
        env.update(self.endpoint.get("env", {}))
        for name, path in self.endpoint.get("secret_env", {}).items():
            env[name] = Path(path).expanduser().read_text().strip()
        command = self.endpoint["command"]
        self.process = await asyncio.create_subprocess_exec(*command,
            cwd=self.endpoint.get("launch_cwd") or None, env=env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, limit=4 * 1024 * 1024,
            start_new_session=os.name != "nt")
        self.fatal = asyncio.get_running_loop().create_future()
        self.connection = connect_to_agent(_Callbacks(self), self.process.stdin,
                                           self.process.stdout, observers=[self._stream_event])
        self.info = await asyncio.wait_for(self.request("initialize", {
            "protocolVersion": 1, "clientInfo": {"name": "minecraft-adapter", "version": __version__},
            "clientCapabilities": {"session": {"compaction": {}}},
        }), 30)
        if self.info.get("protocolVersion") != 1:
            raise ProtocolError("Endpoint did not negotiate ACP v1")
        self.observe("initialized", agent_info=self.info.get("agentInfo"), capabilities=self.info.get("agentCapabilities", {}))

    async def open_session(self, previous=None):
        params = {"cwd": self.endpoint["cwd"], "mcpServers": self.endpoint.get("mcp_servers", [])}
        if self.endpoint.get("session_meta"):
            params["_meta"] = self.endpoint["session_meta"]
        if previous and not self.info.get("agentCapabilities", {}).get("loadSession"):
            raise ProtocolError("Saved session cannot be loaded by this endpoint; refusing to replace it")
        if previous:
            self.available_commands.pop(previous, None)
            params["sessionId"] = previous
            self.session = previous
            self.replaying = True
            try:
                await asyncio.wait_for(self.request("session/load", params, idle_timeout=self.idle_timeout), self.load_timeout)
            except asyncio.TimeoutError as e:
                raise ProtocolError("ACP session/load exceeded its total replay deadline") from e
            finally:
                self.replaying = False
            self.observe("session_loaded", session_id=previous)
        else:
            result = await asyncio.wait_for(self.request("session/new", params), 30)
            self.session = result.get("sessionId")
            if not isinstance(self.session, str) or not self.session:
                raise ProtocolError("Endpoint returned no session ID")
            self.observe("session_recreated" if previous else "session_created", session_id=self.session)
        return self.session

    async def cancel(self, timeout=5):
        # Notification delivery is bounded; it does not prove settlement.
        await asyncio.wait_for(self.connection.cancel(session_id=self.session), timeout)

    def permission_context(self):
        """Describe this client's current policy, never grant a tool invocation."""
        policy = {'server': 'minecraft', 'tools': sorted(self.permission_tools()),
                  'approval': 'allow_once', 'scope': 'same ACP session, active game turn, not session replay'}
        revision = hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()
        active = bool(self.session) and not self.replaying and not self.maintenance_active and bool(self.permission_active())
        return {'policy_revision': revision, 'session_id': self.session, 'active': active,
                'server': policy['server'], 'allow_once_tools': policy['tools'] if active else [],
                'scope': policy['scope']}

    def supports_awareness(self):
        def mapping(value):
            return value if isinstance(value, dict) else {}
        meta = mapping(mapping(self.info).get('_meta'))
        capability = mapping(mapping(mapping(meta.get('io.github.bkrabach.agent-instance')).get('inputContinuity')).get('awareness'))
        return (mapping(meta.get('steering')).get('supported') is True
                and capability.get('version') == 1 and capability.get('activeOnly') is True
                and capability.get('promptIdRequired') is True)

    def supports_input_receipts(self):
        # Steering support alone does not promise native Runtime receipt reads.
        # Preserve each third-party endpoint's actual advertised guarantees.
        meta = self.info.get('_meta') if isinstance(self.info, dict) else None
        steering = meta.get('steering') if isinstance(meta, dict) else None
        return (isinstance(steering, dict) and steering.get('supported') is True
                and steering.get('receiptsMethod') == '_session/input_receipts')

    def _permission(self, session_id, update_call, options):
        call = {**self.tool_calls.get(update_call.get('toolCallId'), {}), **update_call}
        raw = call.get('rawInput') or {}
        valid = (session_id == self.session and isinstance(raw, dict)
                 and raw.get('server') == 'minecraft' and raw.get('tool') in self.permission_tools()
                 and not self.replaying and not self.maintenance_active and self.failed is None
                 and self.permission_active())
        option = next((o for o in options if o.get('kind') == 'allow_once'), None)
        outcome = {'outcome': 'selected', 'optionId': option['optionId']} if valid and option else {'outcome': 'cancelled'}
        self.observe('game_permission_allowed' if valid and option else 'permission_cancelled',
                     tool=raw.get('tool') if isinstance(raw, dict) else None)
        return RequestPermissionResponse.model_validate({'outcome': outcome})

    def _fail(self, error):
        # Never replay an operation after unknown delivery or observer failure.
        if self.failed is None:
            self.failed = error
        if self.fatal is not None and not self.fatal.done():
            self.fatal.set_result(self.failed)

    def _stream_event(self, event):
        value = event.message
        if event.direction == StreamDirection.OUTGOING:
            if 'id' in value and 'method' in value:
                self.requests_sent += 1
                if value['method'] == 'session/prompt':
                    # Read-only observation of SDK-assigned correlation, needed
                    # by negotiated Instance steering. Never allocate our own ID.
                    self.active_prompt_id = value['id']
            return
        self.activity_at = asyncio.get_running_loop().time()
        self.frames += 1
        self.observed_bytes += len(json.dumps(value).encode())
        if 'id' in value and value.get('method') and value['method'] != 'session/request_permission':
            self.observe('unsupported_callback', method=value['method'])
        if value.get('method') != 'session/update' or 'id' in value:
            return
        try:
            message = SessionNotification.model_validate(value.get('params'))
            if (self.foreground or self.replaying) and message.session_id != self.session:
                raise ProtocolError('Update addressed a different ACP session')
            item = wire(message.update)
            if item.get('sessionUpdate') == 'available_commands_update':
                self.available_commands[message.session_id] = {
                    c['name'] for c in item.get('availableCommands', [])[:128]}
                if len(self.available_commands) > 64:
                    self.available_commands.pop(next(iter(self.available_commands)))
            if self.update_handler:
                self.update_queue.put_nowait((self.update_handler, item))
        except Exception as error:
            # SDK observer exceptions are otherwise logged and swallowed. Keep
            # a payload-free application failure visible to the active caller.
            self._fail(error if isinstance(error, ProtocolError) else
                       ProtocolError('Invalid or excessive ACP session updates'))

    async def _collect_updates(self):
        while True:
            handler, item = await self.update_queue.get()
            try:
                if self.failed is None:
                    await handler(item)
            except Exception as error:
                self._fail(error)
            finally:
                self.update_queue.task_done()

    async def _invoke(self, method, params):
        # Generated upstream models validate both directions; extension payloads
        # stay negotiated and are carried by the SDK's documented escape hatch.
        methods = {
            'initialize': (InitializeRequest, self.connection.initialize),
            'session/new': (NewSessionRequest, self.connection.new_session),
            'session/load': (LoadSessionRequest, self.connection.load_session),
            'session/prompt': (PromptRequest, self.connection.prompt),
        }
        if method in methods:
            model, call = methods[method]
            result = await call(**model_to_kwargs(model.model_validate(params), model))
            return wire(result)
        if method.startswith('_'):
            return await self.connection.ext_method(method[1:], params)
        raise ProtocolError('Unsupported ACP request method')

    async def request(self, method, params, update=None, idle_timeout=None):
        if self.transport_closed():
            raise ProtocolError('ACP closed before request')
        foreground = method in ('session/prompt', 'session/load')
        if foreground and self.foreground:
            raise ProtocolError('A prompt or replay is already active on this connection')
        if foreground:
            self.foreground = True
            self.update_handler = update
            self.update_queue = asyncio.Queue(maxsize=1024)
            self.update_worker = asyncio.create_task(self._collect_updates())
        started = asyncio.get_running_loop().time()
        if foreground:
            self.activity_at = started
        reported = started
        frames, size = self.frames, self.observed_bytes
        operation = asyncio.create_task(self._invoke(method, params))
        drain = None
        try:
            while True:
                remaining = max(0, idle_timeout - (asyncio.get_running_loop().time() - self.activity_at)) if idle_timeout else None
                if method == 'session/load':
                    remaining = min(remaining, 5) if remaining is not None else 5
                done, _ = await asyncio.wait([operation, self.fatal], timeout=remaining,
                                             return_when=asyncio.FIRST_COMPLETED)
                if self.failed is not None:
                    raise self.failed
                if operation in done:
                    result = operation.result()
                    if foreground:
                        drain = asyncio.create_task(self.update_queue.join())
                        await asyncio.wait([drain, self.fatal], return_when=asyncio.FIRST_COMPLETED)
                        if self.failed is not None:
                            raise self.failed
                    return result
                now = asyncio.get_running_loop().time()
                if idle_timeout and now - self.activity_at >= idle_timeout:
                    raise ProtocolError(f'ACP {method} stopped making replay progress')
                if method == 'session/load' and now - reported >= 5:
                    self.observe('session_load_progress', frames=self.frames-frames,
                                 bytes=self.observed_bytes-size)
                    reported = now
        except ValidationError:
            self._fail(ProtocolError(f'ACP {method} violated its SDK schema'))
            raise self.failed from None
        except RequestError as error:
            rejected = ProtocolError(f'ACP {method} rejected (code {error.code}; see endpoint logs)')
            # Preserve the SDK's correlated rejection separately from timeout,
            # transport loss and local schema errors. No exception-text parsing.
            rejected.request_rejected = True
            rejected.request_method = method
            rejected.request_error_code = error.code
            raise rejected from None
        except (ConnectionError, OSError) as error:
            self._fail(ProtocolError('ACP transport closed; delivery is unknown'))
            raise self.failed from error
        finally:
            if not operation.done():
                operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
            if drain is not None and not drain.done():
                drain.cancel()
                await asyncio.gather(drain, return_exceptions=True)
            if foreground:
                self.foreground = False
                self.update_handler = None
                self.active_prompt_id = None
                self.update_worker.cancel()
                await asyncio.gather(self.update_worker, return_exceptions=True)
                while not self.update_queue.empty():
                    self.update_queue.get_nowait()
                    self.update_queue.task_done()

    async def prompt(self, text, timeout=None, on_chunk=None, attention_offer=None, snapshot_retained=None, snapshot_key='default'):
        if self.maintenance_active:
            raise ProtocolError('Maintenance is still settling; no game prompt sent')
        self.lifecycle = PromptLifecycle(self.observe)
        parts, characters = [], 0
        messages = {}
        after_tool = False
        self.tool_calls = {}
        permissions = self.permission_context()
        self.observe('permission_context_supplied', **permissions)
        permission_text = (
            'Current adapter permission policy for this turn:\n' + json.dumps(permissions) + '\n'
            'An earlier adapter denial describes that earlier invocation, not a permanent restriction. '
            'If this current policy explicitly covers an operation that is still needed for your permitted activity, '
            'you may try it through the offered tool. Each invocation is checked again; a new denial or human Stop still applies. '
            'This snapshot does not prove the operation succeeded, resolve uncertain prior effects, '
            'grant access on another connection, or extend task scope/deadlines/budgets. '
            'Inspect uncertain or partial effects before retrying.\n'
        )

        async def update(message):
            nonlocal characters, after_tool
            self.lifecycle.update(message)
            kind = message.get("sessionUpdate")
            if kind == "agent_message_chunk" and message.get("content", {}).get("type") == "text":
                chunk = message["content"]["text"]
                # Runtime steering receipts can use empty text envelopes, with
                # no message ID. Only real text establishes answer order/phase;
                # receipt transport and retrieval stay independent of assembly.
                if not chunk:
                    return
                characters += len(chunk)
                if characters > 250_000:
                    raise ProtocolError("ACP output exceeds the observation limit")
                parts.append(chunk)
                message_id = message.get('messageId')
                message_id = message_id if isinstance(message_id, str) else ''
                if len(message_id) > 1024 or (message_id not in messages and len(messages) >= 1024):
                    raise ProtocolError('ACP message identity exceeds the observation limit')
                meta = message.get('_meta')
                details = meta.get('com.microsoft.amplifier.message') if isinstance(meta, dict) else None
                phase = details.get('phase') if isinstance(details, dict) else None
                # Preserve first-observed message order, not last-chunk order.
                # Unidentified output is one append-only legacy message; a tool
                # or a new message ID does not erase text or finish another ID.
                group = messages.setdefault(message_id, {'parts': [], 'phase': None})
                if phase in ('commentary', 'final_answer'):
                    group['phase'] = phase
                if not message_id and after_tool and group['parts']:
                    prior = ''.join(group['parts'])
                    if prior and not prior.endswith('\n\n'):
                        group['parts'].append('\n\n')
                group['parts'].append(chunk)
                after_tool = False
                if on_chunk:
                    await on_chunk(chunk)
            elif kind in ("tool_call", "tool_call_update"):
                after_tool = True
                if parts and not parts[-1].endswith('\n'):
                    parts.append('\n')
                self.observe("tool_update", tool_id=message.get("toolCallId"), status=message.get("status"), title=message.get("title"))
            elif kind == "usage_update":
                self.observe("usage", usage={key: message[key] for key in ("used", "size", "cost") if key in message})
            # Reasoning and raw tool content are not copied into the lab report.

        try:
            from context_snapshot import blocks
            # Stable per-installation key, bounded independently of user text.
            key = hashlib.sha256(snapshot_key.encode('utf-8')).hexdigest()
            result = await asyncio.wait_for(self.request("session/prompt", {
                "sessionId": self.session, "prompt": blocks(self.info, permission_text, text,
                    snapshot_retained, key, permissions['policy_revision']),
                **({"_meta":{"com.microsoft.amplifier.attention":attention_offer}} if attention_offer else {}),
            }, update), timeout)
            unsettled=[tid for tid,call in self.tool_calls.items() if call.get('status') not in ('completed','failed')]
            candidates = [''.join(group['parts']) for group in messages.values()
                          if group['phase'] != 'commentary' and any(group['parts'])]
            final_text = candidates[-1] if candidates else ''
            return {"text": "".join(parts), "final_text": final_text, "stop_reason": result.get("stopReason", "unknown"), 'unsettled_tools':unsettled}
        except asyncio.TimeoutError:
            try:
                await self.cancel()
                self.observe("timeout_cancel_requested")
            except (OSError, RuntimeError):
                pass
            raise

    async def close(self):
        if self.connection:
            await self.connection.close()
        if self.update_worker:
            self.update_worker.cancel()
            await asyncio.gather(self.update_worker, return_exceptions=True)
        if not self.process:
            return
        if self.process.returncode is None:
            try:
                if os.name != "nt":
                    os.killpg(self.process.pid, signal.SIGTERM)
                else:
                    self.process.terminate()
                await asyncio.wait_for(self.process.wait(), 3)
            except (ProcessLookupError, asyncio.TimeoutError):
                if self.process.returncode is None:
                    if os.name != "nt":
                        os.killpg(self.process.pid, signal.SIGKILL)
                    else:
                        self.process.kill()
                    await self.process.wait()
