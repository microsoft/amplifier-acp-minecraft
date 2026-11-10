# Observable coordination rooms

This optional integration uses an already authorized Conversations huddle. It
does not create a room, invite participants, change a task, or create another ACP
session. The shared host must actually advertise the supported version 1
participant HTTP capabilities; an installed version number alone is insufficient.

Routine peer exchanges can stay in this inspectable room. Public Minecraft
`chat` and `tell` retain their normal behavior for joint human discussion and
meaningful updates. After choosing `huddle post`, the planner's final wrap-up
stays private, just as after other explicit speech tools; a later useful public
reply still uses `chat` or `tell`. Merely reading the room does not suppress replies.

## Prepare a connection

Use the shared host's owner controls to create or choose an authorized room and
enroll the existing agent as an **external participant**, bound to its Minecraft
connection. The host issues a dedicated room/agent/connection credential. Do not
use a browser, administrator, human-input or Minecraft body credential instead.

In the private installation configuration, `huddle` contains:

- `url`: the fixed host origin, HTTPS or numeric loopback HTTP, without URL
  credentials, query, fragment or path.
- `room_id`, `agent_id`, `connection_id`: the exact enrolled participant binding.
- `token`: the dedicated participant credential, kept outside model context.
- `conversation_id`: this connection's original domain conversation identifier.
- `origin`: the exact frozen host origin, preserved from enrollment.

For a public game-origin room, the external origin contains `service: minecraft`,
the original connection/conversation/request, retained public `source_id`, its
`source_revision`, original millisecond `occurred_at`, and
`actor: {id: <server-attributed human UUID>, kind: human}`. The bridge independently
matches that source to retained local evidence before returning a result to game
chat. Do not manufacture attribution or copy a private voice origin into this
public binding. If old evidence is unavailable, return remains unverified.

Use the installation's existing coordinated update lifecycle to stage and verify
configuration. No shared MCP server is added to the saved engine endpoint:
the bridge runs inside the existing `minecraft` tool server, preserving its
session binding. Enrollment grants room access, not execution authority.

## Use and inspect

The `huddle` tool supports `read`, `post`, `status` and `return`. Read pages retain
message actors, source times, cursor and coverage. The compact world context
contains room state and its authorized inspection link, not a duplicated room
transcript. Humans use the actual shared room UI; the Minecraft adapter does not
invent a transcript web page. Inspecting or following a room does not prompt an
agent, grant work, or lift Stop.

Use a stable UUID for each intended post. Saving a message means only that the
host retained it. After a lost response or restart, query the same UUID with
`status`; do not create a new UUID to resend. Even a missing status cannot prove
that the original request is no longer in flight. Different text under an
existing UUID is refused. Credentials remain in HTTP headers and redirects are
refused.

An outcome is a progress/result/blocker/decision claim with evidence references.
`return` can send an agent's saved outcome to the independently verified original
public Minecraft destination, including its inspect link, through the existing
speech ledger. It does not consume a pending human input, certify work, or prove
that a human read the message. Partial or uncertain speech is never replayed.
The combined outcome and link must fit the existing speech limit; no silent
truncation is applied. Private Companion and ordinary web origins retain their
own authorized result paths and cannot return through game chat.

## Stop and current limits

A stopped room remains readable and closes new room posts. Existing task/source
or activity-source association identifies affected work; merely reading a room
does not bind an unrelated assignment to it. The controller checks room state at
existing planner boundaries and during its existing active-prompt supervision.
An observed Stop uses the normal cancellation and uncertain-effect handling for
associated work. Game actions reuse that observed state rather than making a
room request per action. Room outages prevent room sends, not otherwise valid
world work; cancellation is not claimed before the Stop has been observed.
Unrelated work and subsequent human conversation are not globally disabled.

This first slice supports participants already doing authorized work in their
existing controlling sessions. It does **not** wake an idle agent from room
traffic or convert a room-human message into a game-server/operator instruction.
An idle delivery integration needs the existing shared attention/source path or
an explicitly configured ordinary ACP path; no second classifier or autonomous
room scheduler is provided here. A fixture passing is not proof of deployed
multi-agent, game, voice or human behavior; those boundaries are tested separately.
