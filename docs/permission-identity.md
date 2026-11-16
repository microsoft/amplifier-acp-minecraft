# Game-tool permission identity

Automatic Minecraft approval is scoped to the current ACP session, announced
call and active game or reply policy. Model arguments do not identify an approved
tool. This does not change the offered game tools, tasks, budgets or Stop rules.

The selected ACP endpoint can advertise
`agentCapabilities._meta["com.microsoft.amplifier.tool"] = {"version":1}`.
For an MCP call, both the initial `tool_call` notification and the matching
permission request's `toolCall` must contain:

```json
{"_meta":{"com.microsoft.amplifier.tool":{
  "version":1,"kind":"mcp","name":"observe","server":"minecraft"
}}}
```

The engine derives this identity from its resolved tool registry. Builtins use
`kind: "builtin"` with their own name and no server; they receive no automatic
Minecraft permission. The permission request must retain the announcement's
session/call IDs, identity, title and raw input. Its ACP `kind` is `other`, as the
native engine has always sent, or the announced kind; neither is authority. The
client retains the
original announcement and refuses duplicate IDs, changed identities, terminal
calls, and missing/conflicting metadata. An advertised but unsupported or
malformed identity contract cannot fall back to legacy interpretation.

The native MCP raw input remains `{server, tool, arguments}`. The outer envelope
must agree with the engine identity. Fields inside `arguments` remain ordinary
tool data, even when named `server`, `tool`, or `_meta`; they grant no authority.
Denied unverified requests are not logged as game-tool approvals, and the
permission observation does not include argument payloads.

## Compatibility

A pre-contract native Runtime is supported only when the selected endpoint
identifies itself as `agent-runtime`, directly or in an Instance's
`_meta["io.github.bkrabach.agent-instance"].backendAgentInfo`. Its legacy contract
requires the exact three-key MCP envelope, object-valued arguments, and the
engine-generated title `minecraft / <tool>`, retained from a prior announcement.
Old native permission requests use `kind: "other"`; this is not authority.
Builtin titles and raw model arguments cannot satisfy this combined contract.

An unknown legacy engine is not authorized merely because its raw arguments
claim `server: "minecraft"`. Such an engine needs a verified producer identity
contract. The new advertised contract is not tied to a Runtime brand or model;
any selected trusted ACP implementation can provide it. Advertising it is a
promise by that peer, not authentication of an arbitrary network endpoint.

The server's domain checks still own world-effect authority. Neither a matching
identity nor an `allow_once` response proves an effect succeeded or permits
replaying an uncertain effect.
