# Returning to the game conversation

An agent can schedule a later conversation turn without waiting for someone to
address it again. The connected engine may call the Minecraft MCP tool
`follow_up`, including outside an active game turn:

```json
{"after_seconds": 300, "goal": "Reconsider whether the crew needs an update on the supermarket plan."}
```

`after_seconds` is an integer from 0 through 3600. A positive value requires a
nonempty `goal` of at most 2000 characters. There is one pending follow-up for
this installation's public game conversation; another positive call replaces
it. `{"after_seconds": 0}` cancels a pending follow-up. The response includes
its `id`, `status`, `goal`, and epoch-millisecond `created_at` and `due_at` when
a reminder exists. Cancellation cannot recall a turn already admitted.

The goal is private planning context, not a chat message. This tool does not
select another server, player, private conversation, or coordination room.
Calling it from an active private or room turn is refused. The same local
installation authentication and MCP permission checks apply as for other tools;
there is no host scheduler, engine-specific adapter, or additional credential.

When due, the existing controller can admit a **conversation-only** turn.
It is labeled `follow_up`, never a human request or a task continuation. The
agent may inspect current context and converse or stay silent. Public speech
uses `chat`/`tell`; the planner's final text is not automatically broadcast.
Task intake/resumption, world actions, and promotion into task-optional play
are refused in this turn. Existing tasks, budgets and authority remain intact.
An engine that holds work from another experience must not treat this reminder
as new human authorization for that work.

Stop cancels a pending reminder. Unresolved effects, disabled conversation,
an installation update gate, an active turn, and the existing reply allowance
prevent admission. Incoming conversation takes precedence. Provider and host
limits still apply. A due time is the earliest eligible time, not a guarantee
that the model runs at that instant; no limits are enlarged to deliver it.

The body saves the reminder and queued input in its existing private workshop
state. Admission consumes its ID in the same saved conversation reservation
before ACP dispatch. A lost acknowledgment, failure or restart never replays
that admitted reminder automatically. A future reminder must be separately
authored; cancelling or replacing a pending one does not settle any old effect.

Engines such as Vigil can discover `follow_up` on the existing Minecraft MCP
server and use this schema for a game place. They retain ownership of deciding
whether and when to arm a reminder; this connector supplies only its delivery
and conversation admission. It does not wake an engine installed elsewhere or
infer a new responsibility from stored notes.
