"""Minimal ACP v1 stdio client. Endpoint ownership stays outside the lab."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import signal

__version__ = "0.1.0"

# One source for both callback enforcement and the agent-visible policy.
GAME_TOOLS = frozenset({'observe','survey','inspect','find','chat','move','follow','gather','craft','place','build','give','stop','work_begin','work_report','work_reopen','map','plan_route','dig','set_open','tell','work_note','inventory','entities','shear','furnace','container','attention_watch','attention_watches','attention_cancel','read_sign','write_sign','screenshot','screenshots','screenshot_read'})


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

    def transport_closed(self):
        """Known local closure only; this makes no ACP request or health promise."""
        return (self.process is None or self.process.returncode is not None
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

    async def request(self, method, params, update=None, idle_timeout=None):
        self.next_id += 1
        request_id = self.next_id
        await self.send({"id": request_id, "method": method, "params": params})
        frames, size, reported = 0, 0, asyncio.get_running_loop().time()
        while True:
            try:
                line = await asyncio.wait_for(self.process.stdout.readline(), idle_timeout) if idle_timeout else await self.process.stdout.readline()
            except asyncio.TimeoutError as e:
                raise ProtocolError(f"ACP {method} stopped making replay progress") from e
            if not line:
                raise ProtocolError("ACP closed before replying")
            frames += 1
            size += len(line)
            now = asyncio.get_running_loop().time()
            if method == 'session/load' and now - reported >= 5:
                self.observe('session_load_progress', frames=frames, bytes=size)
                reported = now
            value = json.loads(line)
            if value.get("jsonrpc") != "2.0":
                raise ProtocolError("Invalid JSON-RPC frame")
            if "method" not in value and value.get("id") == request_id:
                if "error" in value:
                    code = value['error'].get('code')
                    code = code if isinstance(code, int) else 'unknown'
                    raise ProtocolError(f"ACP {method} rejected (code {code}; see endpoint logs)")
                return value.get("result", {})
            if "method" in value and "id" in value:
                if value["method"] == "session/request_permission":
                    params = value.get('params', {})
                    update_call = params.get('toolCall', {})
                    call = {**self.tool_calls.get(update_call.get('toolCallId'), {}), **update_call}
                    raw = call.get('rawInput') or {}
                    # Only this session's registered game server, using structured
                    # tool metadata; a friendly display title never grants access.
                    valid = (params.get('sessionId') == self.session and isinstance(raw, dict)
                        and raw.get('server') == 'minecraft' and raw.get('tool') in GAME_TOOLS
                        and not self.replaying and self.permission_active())
                    option = next((o for o in params.get('options', []) if o.get('kind') == 'allow_once'), None)
                    outcome = {'outcome':'selected','optionId':option['optionId']} if valid and option else {'outcome':'cancelled'}
                    self.observe('game_permission_allowed' if valid and option else 'permission_cancelled', tool=raw.get('tool') if isinstance(raw,dict) else None)
                    await self.send({'id':value['id'],'result':{'outcome':outcome}})
                else:
                    await self.send({"id": value["id"], "error": {"code": -32601, "message": "Client capability not offered"}})
                    self.observe("unsupported_callback", method=value["method"])
            elif value.get("method") == "session/update" and update:
                message = value.get("params", {})
                if message.get("sessionId") != self.session:
                    raise ProtocolError("Update addressed a different ACP session")
                item = message.get('update', {})
                if item.get('sessionUpdate') in ('tool_call','tool_call_update'):
                    tid = item.get('toolCallId')
                    self.tool_calls[tid] = {**self.tool_calls.get(tid, {}), **{k:v for k,v in item.items() if v is not None}}
                await update(item)

    async def prompt(self, text, timeout, on_chunk=None):
        parts, final_parts, characters = [], [], 0
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
            nonlocal characters
            kind = message.get("sessionUpdate")
            if kind == "agent_message_chunk" and message.get("content", {}).get("type") == "text":
                chunk = message["content"]["text"]
                characters += len(chunk)
                if characters > 250_000:
                    raise ProtocolError("ACP output exceeds the observation limit")
                parts.append(chunk)
                final_parts.append(chunk)
                if on_chunk:
                    await on_chunk(chunk)
            elif kind in ("tool_call", "tool_call_update"):
                final_parts.clear()
                if parts and not parts[-1].endswith('\n'):
                    parts.append('\n')
                self.observe("tool_update", tool_id=message.get("toolCallId"), status=message.get("status"), title=message.get("title"))
            elif kind == "usage_update":
                self.observe("usage", usage={key: message[key] for key in ("used", "size", "cost") if key in message})
            # Reasoning and raw tool content are not copied into the lab report.

        try:
            result = await asyncio.wait_for(self.request("session/prompt", {
                "sessionId": self.session, "prompt": [{"type": "text", "text": permission_text}, {"type": "text", "text": text}],
            }, update), timeout)
            unsettled=[tid for tid,call in self.tool_calls.items() if call.get('status') not in ('completed','failed')]
            return {"text": "".join(parts), "final_text": "".join(final_parts), "stop_reason": result.get("stopReason", "unknown"), 'unsettled_tools':unsettled}
        except asyncio.TimeoutError:
            try:
                await self.cancel()
                self.observe("timeout_cancel_requested")
            except (OSError, RuntimeError):
                pass
            raise

    async def close(self):
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
