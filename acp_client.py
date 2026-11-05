"""Minimal ACP v1 stdio client. Endpoint ownership stays outside the lab."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import signal

__version__ = "0.1.0"

# One source for both callback enforcement and the agent-visible policy.
GAME_TOOLS = frozenset({'observe','survey','inspect','find','chat','move','follow','cancel_movement','gather','craft','place','build','give','stop','work_begin','work_report','work_reopen','map','plan_route','dig','set_open','tell','work_note','inventory','entities','shear','furnace','container','attention_watch','attention_watches','attention_cancel','read_sign','write_sign','screenshot','screenshots','screenshot_read','conversation','till'})


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
        self.next_id = 0
        self.session = None
        self.info = None
        self.write_lock = asyncio.Lock()
        self.tool_calls = {}
        self.permission_active = lambda: False
        self.load_timeout, self.idle_timeout = load_timeout, idle_timeout
        self.replaying = False
        self.reader = None
        self.pending = {}
        self.active_prompt_id = None

    def transport_closed(self):
        """Known local closure only; this makes no ACP request or health promise."""
        return (self.process is None or (self.reader is not None and self.reader.done()) or self.process.returncode is not None
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
        self.reader = asyncio.create_task(self._read_frames())
        self.info = await asyncio.wait_for(self.request("initialize", {
            "protocolVersion": 1, "clientInfo": {"name": "minecraft-adapter", "version": __version__},
            "clientCapabilities": {},
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

    async def send(self, value):
        async with self.write_lock:
            self.process.stdin.write((json.dumps({"jsonrpc": "2.0", **value}) + "\n").encode())
            await self.process.stdin.drain()

    async def cancel(self):
        await self.send({"method": "session/cancel", "params": {"sessionId": self.session}})

    def permission_context(self):
        """Describe this client's current policy, never grant a tool invocation."""
        policy = {'server': 'minecraft', 'tools': sorted(GAME_TOOLS),
                  'approval': 'allow_once', 'scope': 'same ACP session, active game turn, not session replay'}
        revision = hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()
        active = bool(self.session) and not self.replaying and bool(self.permission_active())
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

    async def _callback(self, value):
        if value['method'] != 'session/request_permission':
            await self.send({'id': value['id'], 'error': {'code': -32601, 'message': 'Client capability not offered'}})
            self.observe('unsupported_callback', method=value['method'])
            return
        params = value.get('params', {})
        update_call = params.get('toolCall', {})
        call = {**self.tool_calls.get(update_call.get('toolCallId'), {}), **update_call}
        raw = call.get('rawInput') or {}
        valid = (params.get('sessionId') == self.session and isinstance(raw, dict)
                 and raw.get('server') == 'minecraft' and raw.get('tool') in GAME_TOOLS
                 and not self.replaying and self.permission_active())
        option = next((o for o in params.get('options', []) if o.get('kind') == 'allow_once'), None)
        outcome = {'outcome': 'selected', 'optionId': option['optionId']} if valid and option else {'outcome': 'cancelled'}
        self.observe('game_permission_allowed' if valid and option else 'permission_cancelled',
                     tool=raw.get('tool') if isinstance(raw, dict) else None)
        await self.send({'id': value['id'], 'result': {'outcome': outcome}})

    async def _read_frames(self):
        # One reader owns stdout. Prompt notifications retain wire order while
        # independent steering/receipt responses route by their own request ID.
        try:
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    raise ProtocolError('ACP closed before replying')
                value = json.loads(line)
                if not isinstance(value, dict) or value.get('jsonrpc') != '2.0':
                    raise ProtocolError('Invalid JSON-RPC frame')
                if 'method' not in value:
                    pending = self.pending.get(value.get('id'))
                    if pending:
                        pending[1].put_nowait((value, len(line)))
                    continue
                if value.get('method') == 'session/update':
                    message = value.get('params', {})
                    if (self.active_prompt_id is not None or self.replaying) and message.get('sessionId') != self.session:
                        raise ProtocolError('Update addressed a different ACP session')
                    item = message.get('update', {})
                    if item.get('sessionUpdate') in ('tool_call', 'tool_call_update'):
                        tid = item.get('toolCallId')
                        self.tool_calls[tid] = {**self.tool_calls.get(tid, {}), **{k: v for k, v in item.items() if v is not None}}
                if 'id' in value:
                    await self._callback(value)
                for method, queue in tuple(self.pending.values()):
                    if method in ('session/prompt', 'session/load'):
                        queue.put_nowait((value, len(line)))
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # A broken pipe is ambiguous delivery, never a reason to resend work.
            for _, queue in tuple(self.pending.values()):
                queue.put_nowait((error, 0))

    async def request(self, method, params, update=None, idle_timeout=None):
        if self.reader is not None and self.reader.done():
            raise ProtocolError('ACP closed before request')
        if method == 'session/prompt' and self.active_prompt_id is not None:
            raise ProtocolError('A prompt is already active on this connection')
        self.next_id += 1
        request_id = self.next_id
        queue = asyncio.Queue()
        self.pending[request_id] = (method, queue)
        if method == 'session/prompt':
            self.active_prompt_id = request_id
        frames, size, reported = 0, 0, asyncio.get_running_loop().time()
        try:
            await self.send({'id': request_id, 'method': method, 'params': params})
            while True:
                try:
                    value, length = await asyncio.wait_for(queue.get(), idle_timeout) if idle_timeout else await queue.get()
                except asyncio.TimeoutError as error:
                    raise ProtocolError(f'ACP {method} stopped making replay progress') from error
                if isinstance(value, Exception):
                    raise value
                frames += 1
                size += length
                now = asyncio.get_running_loop().time()
                if method == 'session/load' and now - reported >= 5:
                    self.observe('session_load_progress', frames=frames, bytes=size)
                    reported = now
                if 'method' not in value:
                    if 'error' in value:
                        code = value['error'].get('code')
                        code = code if isinstance(code, int) else 'unknown'
                        raise ProtocolError(f'ACP {method} rejected (code {code}; see endpoint logs)')
                    return value.get('result', {})
                if value.get('method') == 'session/update' and update:
                    await update(value.get('params', {}).get('update', {}))
        finally:
            self.pending.pop(request_id, None)
            if method == 'session/prompt' and self.active_prompt_id == request_id:
                self.active_prompt_id = None

    async def prompt(self, text, timeout, on_chunk=None, attention_offer=None):
        parts, characters = [], 0
        messages = {}
        after_tool = False
        self.tool_calls = {}
        permissions = self.permission_context()
        self.observe('permission_context_supplied', **permissions)
        permission_text = (
            'Current adapter permission policy for this turn:\n' + json.dumps(permissions) + '\n'
            'An earlier adapter denial describes that earlier invocation, not a permanent restriction. '
            'If this current policy explicitly covers an operation that is still needed for your accepted task, '
            'you may try it through the offered tool. Each invocation is checked again; a new denial or human Stop still applies. '
            'This snapshot does not prove the operation succeeded, resolve uncertain prior effects, '
            'grant access on another connection, or extend task scope/deadlines/budgets. '
            'Inspect uncertain or partial effects before retrying.\n'
        )

        async def update(message):
            nonlocal characters, after_tool
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
            result = await asyncio.wait_for(self.request("session/prompt", {
                "sessionId": self.session, "prompt": [{"type": "text", "text": permission_text}, {"type": "text", "text": text}],
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
        if self.reader:
            self.reader.cancel()
            await asyncio.gather(self.reader, return_exceptions=True)
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
