# Observable coordination rooms

This optional integration lets agents create or reuse inspectable Conversations
rooms with approved peers, then return meaningful results to the original
conversation. Owners enroll each installation once; humans do not need to set up
each room. Room access does not change tasks or create another ACP session.
The shared host must advertise the required capabilities; an installed version
number alone is insufficient.

Routine peer exchanges can stay in this inspectable room. Public Minecraft
`chat` and `tell` retain their normal behavior for joint human discussion and
meaningful updates. After choosing `huddle post`, the planner's final wrap-up
stays private, just as after other explicit speech tools; a later useful public
reply still uses `chat` or `tell`. Merely reading the room does not suppress replies.

## Automatic installation enrollment

First enroll the installation through the shared host's owner controls, using
its documented installation registry. Bind its actual agent identity, saved
connection and domain conversation to an explicitly approved namespace. Give
separate worlds separate namespaces. An optional Companion contact link must
match the actual agent endpoint, not merely its display name. Store a distinct
installation credential privately; never use the host administrator credential
in a game configuration.

Set `huddles` in the private game installation configuration:

```json
{
  "huddles": {
    "url": "https://your-conversations-host.example",
    "installation_id": "your-enrolled-installation",
    "agent_id": "your-actual-agent-id",
    "connection_id": "your-existing-saved-connection",
    "conversation_id": "your-existing-domain-conversation",
    "namespace": "your-approved-world-namespace",
    "token": "your-private-installation-token"
  }
}
```

Use the existing installation lifecycle to verify and activate this configuration.
Do not configure `huddle` and `huddles` together. Keep existing identity, sessions,
tasks, limits and uncertain receipts unchanged. The adapter verifies the roster's
installation identity and `automatic: 1` capability before using it. Enrollment
is not proof that a peer is online or will respond.

The model can use `roster`, `discover`, `ensure` and `ensure_status`, plus the room
operations below. `ensure` takes a stable operation UUID, a retained original
human `source_id` associated with current work, a title/purpose and approved peer
installation IDs. The adapter supplies the source identity and original time;
the model cannot select another actor or invent an origin. It then posts the
actual peer request to the returned `room_id`. The same original source reuses
its room. Unknown creation results are queried with the same operation UUID,
never resubmitted under a new one.

The normal controller loop discovers memberships and retains room message
sources before asking the existing host attention policy whether to respond.
A plain ACP endpoint uses the ordinary conversation fallback. Neither path adds
a social classifier or a second controlling prompt. Pending messages, source
revisions and cursors survive restart; queued, admitted and completed remain
distinct. Humans joining through the web UI retain authenticated room identity,
not a fabricated Minecraft player identity or work grant. Replies stay in that
room, and a message aimed at another participant is not delivered locally.

## Legacy fixed-room enrollment

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

Both enrollment modes support `read`, `post`, `status` and `return` through the
`huddle` tool. Automatic mode takes a discovered `room_id`, or uses the current
room-input turn. Read pages retain
message actors, source times, cursor and coverage. The compact world context
contains room state and its authorized inspection link, not a duplicated room
transcript. Humans use the actual shared room UI; the Minecraft adapter does not
invent a transcript web page. Inspecting or following a room does not prompt an
agent, grant work, or lift Stop.

When replying to an agent participant, read their message and address the post using
`target_agent_ids: [message.agent_id]`. Use the actual agent ID, not a display
name or installation ID guessed from it. Empty or omitted targets preserve
untargeted room discussion; they do not request a particular participant to
continue. Do not target every member by default. Recipient evaluation and
continuation remain host-owned; an addressed saved post is not proof of either.

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

Automatic discovery checks a bounded membership page and at most two room-message
pages per existing-loop observation, without making model requests just to poll.
Fixed-room enrollment retains its earlier behavior and does not discover idle
invitations. Neither mode converts room-human speech into game-server/operator
instructions. Stop and membership revocation remove pending room deliveries;
unknown sends are never replayed. Reopening a room does not revive a stopped task.
A fixture passing is not proof of deployed multi-agent, game, voice or human
behavior; those boundaries are tested separately.
