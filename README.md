# Minecraft ACP adapter

Part of [Amplifier Constellation](https://github.com/microsoft/amplifier-constellation).

Connect independent ACP agents to Minecraft as ordinary players. Each player has
its own process, inventory, credentials, working session and task limits.
Minecraft owns the shared world and public conversation. Mineflayer provides
the player's body; the adapter gives its agent scoped Minecraft tools through
HTTP MCP supplied during standard ACP session setup.

The agent can use Constellation, Codex, or another ACP implementation that supports
HTTP MCP. No model SDK, shared agent memory, custom Minecraft mod, or Agent
Instance management API is required. Optional integrations are described below.

## Set up a player

Requirements: Node 22+, Python 3.12+, a Minecraft Java Edition server compatible
with Mineflayer, and a separately authenticated ACP agent. The included game
fixtures target Java Edition 1.21.1. The Minecraft client, server and game assets
are obtained separately; this repository does not distribute them.

```sh
git clone https://github.com/microsoft/amplifier-acp-minecraft.git
cd amplifier-acp-minecraft
npm ci --ignore-scripts
```

Copy `config.example.json` and `endpoint.example.json` to a private installation
directory as `config.json` and `endpoint.json`. Set the server address, a unique
player name, an unused control port and a long random control token. Set the
endpoint command to an ACP executable and its working directory. Keep installation
directories private (0700) and configuration files owner-readable only (0600).

The example's offline authentication is for an isolated test server whose access
you control. Offline names do not verify identity. For an authenticated server,
configure Mineflayer's Microsoft authentication and licensed player accounts.
Human players also need their normal Java Edition account.

Start the body and controller in separate terminals:

```sh
node body.cjs /private/your-player/config.json
python3 adapter.py --home /private/your-player
```

Repeat with a separate directory, player name and port for every agent. The
`ops/minecraft-body@.service` and `ops/minecraft-agent@.service` files are optional
Linux user-service templates. Adjust their application and Node paths to the
installation before enabling them; `%h` refers to the service user's home.

The body listens on loopback. Its MCP and control requests require a bearer token,
and browser origins are rejected. A remote ACP agent needs a trusted route back
to the MCP endpoint, such as an SSH tunnel and an `mcp_url` override. A loopback
address is interpreted on the machine where the connecting process runs.

Planner turns and the default `observe` tool use a recent working view: current
world facts and conversation, the last five progress reports, and the last five
exact action receipts. Repeated historical observations and duplicate event
payloads are omitted with explicit counts/markers. Task identity, authority,
deadlines, consumed turns and uncertainty remain unchanged. `work_report` and
`work_note` return the same recent task view after saving full evidence.
Use `observe(detail="full")` to inspect older retained details when needed.
Owner-local `/state` and durable evidence remain full; `/observation` is the
authenticated recent view. This is a presentation projection, not evidence that
omitted actions succeeded, messages were handled, or responsibilities ended.

## Newer servers and crossplay

The default body uses Java protocol 1.21.1. It can also join Paper 26.3 through
ViaVersion and ViaBackwards, with the body still configured as `version: "1.21.1"`.
This does not give the body native knowledge of newer blocks or recipes; translated
blocks may have older appearances and newer mechanics need separate validation.
Human clients can use the server's native version. Geyser and Floodgate can provide
Bedrock connections and account linking outside this adapter.

For this translated connection the adapter leaves only the unused recipe-book UI
packet opaque. Inventory, entities, blocks and action results remain decoded and
verified. Inventory clicks wait for a matching server ping response to drain late
inventory updates before the next operation. Container transfers accept only the
exact empty ViaBackwards bookkeeping component for ordinary supplies, preserve it
in clicks, and continue refusing actual custom or enchanted items.

Crafting, container and survival regressions can run against a disposable
`level-name=container-fixture` world. Pass its `--properties` and `--node`, plus
`--port` when connecting through a version proxy. Crafting and survival require an
explicit `--log`; containers require `--out`. Never point these fixtures at a
shared world: they create blocks, creatures and inventory for their checks.

## Optional player screenshots

[Enable on-demand screenshots](docs/screenshots.md) to let an agent capture its
Minecraft view, save it in its own workspace and explicitly share the image
through an ACP client such as Slack. Rendering stays in this adapter; image
inspection and attachment stay in the agent runtime and client.

## Talk and work together

With legacy routing, join through Minecraft's Multiplayer screen and address a configured
player, for example `BuilderOne, help design a bridge.` Group prefixes such as
`Team,` address all configured agents. After a direct address, that human's
follow-ups continue to the same player for ten minutes. Addressing a different
player transfers conversational focus. Other chat remains observable context
without automatically starting a model turn.

Explicit requests from configured peers can start bounded turns. The defaults
allow four peer requests per hour within forty minutes of human activity.
`tell(player, text, intent)` makes the recipient explicit. `intent=request` asks
for action; `update` and `ack` add visible FYI/ACK markers and remain context
without waking the recipient in legacy routing. With Instance attention enabled,
the host evaluates fresh public messages instead. This is a public chat convention, not a hidden
coordination channel or an ACP extension. Configure `aliases` consistently on
all players when using shorter names. Private whispers are excluded from shared
context; replies from this adapter currently appear publicly.

The tools cover observation, terrain maps, route planning, movement, following,
gathering, digging, tilling, crafting, inventory, containers, furnaces, placement, small
build patterns, signs, item handoffs, chat and Stop. Physics and movement run
without model calls. Agent tools expose no arbitrary shell, RCON, teleport or
item creation. Operator-only RCON helpers live under `ops/`.

Movement verifies arrival height and reports obstruction or stalled progress.
The body's vanilla player collision width matches Minecraft's float dimensions;
this prevents edge-overlap corrections during sprint-jumps onto full blocks.
It does not relax server collision checks or grant new movement capabilities.
For level activities that prohibit jumping, select `mode: "walk_only"` for both
`plan_route` and `move`; ordinary pathfinding permits other traversal strategies.
Level routes report `current_feet` and reject a fractional-height start as
`non_level_start` before moving. A clear center cell alone is not enough when
the player's edge is resting on a neighboring slab.
Digging checks footing and adjacent liquids. Crafting and placement refresh the
server inventory. Sign writes verify the server's text echo and can reject stale
edits with `expected_lines`. Item drops remain physical world interactions:
another nearby player may collect them, so verify the recipient's inventory.

`place.facing` selects a cardinal direction for ordinary signs (text front), beds
(foot toward head), stairs (uphill direction), and furnaces, blast furnaces or
smokers (front). Placement checks the observed server block properties before
reporting success. An orientation mismatch may have placed a block: inspect it
instead of repeating the action. Stair half and shape remain determined by the
support face and surroundings; the result includes their observed properties.
Other block types retain ordinary placement without an explicit facing.

`tests/facing_live.py --node /path/to/node --properties /path/to/server.properties
--out /path/to/results.json` checks twenty furnace/stair orientations through the
real body, with independent server block-state confirmation. It accepts only a
loopback disposable `facing-fixture`, `farming-fixture` or `container-fixture`
world and uses no model calls. Never run fixture tests against a shared world.

`tests/movement_live.py --node /path/to/node --properties /path/to/server.properties
--out /path/to/results.json` checks climbs, descents and blocked head clearance
through the body against a loopback-only disposable `movement-fixture` or
`container-fixture` world. Use `--port` for its translation proxy. The fixture
creates test geometry and must never target a shared world. It uses no model.

`container` inspects ordinary chests (single/double) and barrels, or deposits and
withdraws 1–64 items. It checks reach without moving, uses authoritative server
snapshots after every click, and verifies source/destination totals. Ordinary
supplies may be selected by name. Tools, named or enchanted items, and other
component-bearing stacks require explicit `source_slot` and `source_item_revision`
from a fresh inspection, alongside `contents_revision` and `conversation_revision`.
Inspection reports window-relative slots and item revisions for both storage and
player inventory. A selected transfer takes only that exact stack and uses empty
destination slots, preserving its wear, name, enchantments and components. It
never substitutes another same-name item or merges selected stacks.

Insufficient supplies or space and stale selection fail before transferring.
Concurrent changes, ignored clicks or missing acknowledgements stop the batch;
partial results are unconfirmed and must not be replayed blindly. Inspect first.
`recover` can return a held cursor only to its original source when the item
identity still matches and the original count is not exceeded. The window stays
open when cursor state is unresolved, preventing accidental dropped leftovers.
Shared storage still needs coordination; a successful transfer does not establish
exclusive ownership or guarantee its future contents.

The optional `tests/containers_live.py` regression requires a **separate disposable
server** on a non-production port with `level-name=container-fixture`. Pass
`--node`, `--properties`, and `--out` explicitly. It creates fixture supplies in
that world; it does not use a model or modify the workshop world.

## Continuing tasks and recovery

A routed human request can authorize `work_begin`. The agent reports progress
with `work_report`, choosing running, waiting, blocked, or review. Defaults are
12 ACP turns and 40 minutes per task, with 30 ACP turns per player per hour.
The hourly limit defers planner starts without consuming queued messages or
renewing the task's deadline. Bounded attention checks continue while authorized
work is waiting, so a delivery can be noticed before its watch expires. A wake
marks that existing task ready; it does not bypass planner capacity or start an
ACP prompt. Watch expirations and decision-service quotas still apply, and no
expired watch is revived. State survives controller restarts.

Public hourly-capacity notices are sent once per wait and at most once every
15 minutes per installation. A brief resumption or controller restart does not
reset that cadence. The last attempted notice time is persisted before sending
in `capacity-notice.json`, so an ambiguous delivery is not immediately repeated.
Every capacity wait and resumption remains observable; this only limits repeated
public notices, not conversation delivery, interruption notices, or work limits.

Stop cancels work and revokes the current action lease. Interrupted work requires
inspection. Clean model turn limits can continue only when tools have settled and
the body is idle, within the existing task budget. `review` means the agent has
reported completion; it is not independent verification of the world.

An operator can nominate configured peers to review a particular task:

```sh
python3 cli.py --home /private/your-player --reviewer LeadOne task 'Help LeadOne finish the agreed inn.'
```

This records the reviewer grant on the human request, not in model-authored text.
After reporting review, the agent may use `work_reopen` for a fresh public request
from that reviewer that corrects work within the existing goal. It cites the
incoming event ID and explains the correction. Each reopening consumes a task
turn; at most three are allowed. Task identity, deadline and limits remain
unchanged. FYI messages, other peers, replayed requests and stopped, expired,
blocked or interrupted tasks cannot use this path. Agents must judge scope;
the adapter checks the named relationship, evidence and remaining authority.

Queued messages survive body restarts and remain queued while ACP connects or
loads history. A failed connection does not consume a work turn or the hourly
ACP turn allowance. Session loading permits up to three minutes of replay with a separate
30-second inactivity limit; replay never approves tools. Reconnection preserves
the saved session or reports a failure rather than silently replacing it.
If the local ACP process or pipe has closed between turns, the controller
reconnects and loads that saved session before reserving another turn. This check
makes no model or protocol request. A disconnect after a turn starts still uses
interrupted-turn recovery; prompts and uncertain actions are not blindly replayed.

`work_note` records a reassessment without renewing authority. An operator may
use `/resume-reviewed` for an idle blocked task after inspecting its receipts
and current state. Supply its task ID, current generation and a concrete reason.
The original request, deadline and remaining budget are preserved. Stopped,
expired, exhausted or active tasks cannot be resumed through this operation.

With `automatic_recovery: true` and a current runtime helper, `/continuation`
evaluates durable action receipts and fresh world observations. It can resume an
interrupted responsibility only when every recorded action settled successfully,
the body is idle, and the original budget remains. Partial or uncertain effects
still require review. At most two automatic reconciliations are allowed per task;
none replay the old prompt or actions. Reconciliation is recorded as evidence.
The generic advice policy lives in the runtime; game observations, receipts and
enforcement live here. The setting is off unless explicitly enabled.

When less than two minutes remain, the controller saves a budget checkpoint
instead of starting a turn too short to do useful work. A peer request may still
receive an inspection or reply, but cannot authorize mutations after work stops
or expires. Only a fresh routed human request can authorize a new responsibility.

Each turn permits at most 24 mutating calls; builds and gathers
also have per-action limits. Structured permission metadata can approve only a
named tool from the active session's Minecraft MCP server, once. Other permission
requests are cancelled. These controls do not change tools or authority already
built into the agent itself.

## Programmatic control

```sh
python3 cli.py --home /private/your-player state
python3 cli.py --home /private/your-player task 'Help build a bridge.'
python3 cli.py --home /private/your-player stop
```

The authenticated loopback API includes GET `/state`, `/status`, `/inbox` and
POST `/task`, `/turn`, `/finish`, `/stop`, `/action`, `/reply`, `/recover`, `/notice`
and `/resume-reviewed`, `/continuation`. POST `/mcp` serves the scoped game tools.
`/task` accepts an optional `reviewers` array. GET `/inbox/peek` reads the durable
queue; `/turn` validates and claims the supplied `message_ids` against
the current generation. The legacy `/inbox` consumes messages immediately and
should not be used before connection setup. Observers use `/state`.
Control credentials stay in the private installation.

## Current connection permissions

Each normally admitted ACP turn includes the adapter's current permission policy:
its revision, session scope and tools eligible for one-call approval. The list
comes from the same allowlist used to answer ACP permission callbacks. This lets
an agent distinguish an old adapter denial from the current connection policy
after a tool has been added or repaired. It does not wake an idle agent, replace
its session, add a task or renew a budget.

The snapshot is context, not an approval token. Each callback still checks the
session, tool metadata, live turn status and replay state. Human Stop or a new
denial takes precedence, and an uncertain prior operation still needs inspection.
The adapter owns this connection-specific policy; agent implementations remain
free to reason about capability changes without Minecraft-specific runtime code.

## Action timeouts

`cancel_movement` abandons only an in-flight `move` or `follow` while preserving
its existing task, turn deadline and consumed budget. Wait for the original action
to settle, inspect the actual position, and then choose another route. It refuses
to cancel a different action; an idle call is a no-op. `stop` still ends the whole
assignment, including when a human asks to stop. Unsettled workers keep the body
busy and remain subject to the action timeout; cancellation never proves arrival.

The authenticated operator-only `/resume-reviewed` endpoint can also recover an
accidentally stopped assignment with `resume_stopped: true`, its exact `task_id`,
current `generation`, and a concrete `reason`. Review the stop's origin and settled
effects first. A human stop requires subsequent human authorization; this is never
automatic recovery or an agent tool. Normal recovery still refuses stopped work.
The original deadline, task identity and consumed turn budget remain unchanged;
expired/exhausted or active tasks cannot be resumed. Unknown work is not replayed.

A movement action has a 60-second limit. On timeout the body cancels the old
action generation and waits briefly for its worker to settle. A settled movement
failure leaves the existing turn available for inspection and a progress report;
it does not retry the route, count as arrival, or renew any budget. Human Stop and
disconnect still close the turn. Other action timeouts retain conservative
closed-turn behavior. If cancellation has not settled, the turn closes and the
body remains busy until cleanup actually finishes, preventing overlapping actions.
Failure receipts identify timeout, worker settlement and whether the turn remained
open. An uncertain receipt remains uncertain even if its worker has returned.

## Optional context, decisions and watches

The optional `agent-instance.context/1` provider makes recent public game events,
action receipt metadata, presence and task status discoverable through an
authorized context layer. It uses a separate `context_token` and a non-owner game
audience grant. Private owner conversations do not become visible to the game.
The history is bounded and reports its coverage. Standard ACP does not itself
merge conversations or authorize cross-surface retrieval.

Shared history uses explicit projections: public chat text, task/progress
summaries, and action IDs, names, lifecycle stages and bounded outcome flags.
It never serializes arbitrary local events. Tool arguments, returned payloads,
exception strings and nested progress observations remain owner-local, including
attempted `tell` messages. Unknown event types are omitted. An action result only
records that the call returned; it does not independently verify task completion.
These projections do not modify the stored history or owner access to it.
Outgoing `chat`, public `tell`, replies and notices record the actual text handed
to public chat separately, so shared readers can still follow the conversation.
Final replies use up to eight paced chat messages, bounded by the platform's
UTF-16 limit. Longer replies end with an explicit shortening notice instead of
silently dropping the end. Delivery stops if the public conversation changes;
delivery counts describe what was sent, without logging the reply payload.
A failed send does not create that record; it is not proof of remote delivery.

For a same-machine [Agent Instance](https://github.com/microsoft/amplifier-constellation-instance):

```sh
python3 ops/register_context.py --home /private/your-player --agent-home /private/agent-instance
```

Restart the body and controller after changing the audience binding. Remote
registration needs a trusted endpoint and separately scoped provisioning.
Source retrieval is read-only; inspecting game context from another interface
does not grant game-control tools.

Optional decision support uses the generic
[Constellation runtime](https://github.com/microsoft/amplifier-constellation-runtime)
CLI. A private `decision_attention` configuration supplies its command, home,
backend and credential file. Credentials are a mode-0600 environment mapping and
are not sent to the planner. The default waiting policy can request a planner
turn when changed observations appear relevant; the planner verifies the evidence.
`policy: "agent-assessment-v2"` enables general attention, reflection and
coordination questions, in `shadow` or `advisory` mode. Decisions never execute
game actions, create tasks, extend deadlines or grant permissions.

With `agent_watches: true` and a runtime supporting `watch`, agents can author
bounded conditions through `attention_watch`, `attention_watches` and
`attention_cancel`. The adapter supplies public messages, tool receipts and
world observations. A matching watch may wake only an authorized waiting task;
otherwise it becomes advice at a normal turn boundary. Stop, expiry and stale
observations prevent a wake. The tool defaults to `initial_check: current_state`,
so conditions already satisfied when registering are not lost. `new_events`
retains the older baseline behavior. An exact `predicate` can inspect a projected
environment fact without a model call: for example `environment:self`, pointer
`/inventory_counts/oak_log`, `op: gte`, `value: 12`. Inventory stacks are aggregated,
and positions use the containing block (floor), including negative coordinates.
Use `any_of` for semantic peer reports. Predicates and semantic conditions are
alternatives; their receipts and model-call counts remain separate.

Message projection requires a helper supporting `responsibility-watch-v7`.
Upgrade the helper before this adapter. The bridge supplies the server-observed
author, the first explicit `@recipient`, and the visible `tell` convention:
`[FYI]` means `update`, `[ACK]` means `ack`, and an addressed message without a
marker has the default `request` intent. Unaddressed chat has no inferred intent;
later mentions and quoted addresses are not recipients. These are routing facts,
not a claim that the message actually satisfies a request or completion condition.

Agents may use a string `any_of` branch as before, or an object such as
`{"condition":"Lena asks Bea for help", "message":{"authors":["Lena"],
"recipients":["Bea"],"intents":["request"]}}`. Exact filters avoid decision calls
for wrong recipients or message types before semantic evaluation. Completion
watches should allow updates and need not require a direct recipient. The
`watch_filtered` receipt records filtered evidence and whether other eligible
evidence still called the model. It is separate from a semantic hold, a pending
notification, or a gate that actually admits a planner turn. Saved watches are
preserved, not silently converted or rearmed by the upgrade.

See the runtime's [assessment](https://github.com/microsoft/amplifier-constellation-runtime/blob/main/docs/assessment.md)
and [watch](https://github.com/microsoft/amplifier-constellation-runtime/blob/main/docs/watches.md)
contracts. Disabling these optional helpers leaves ordinary ACP operation available.

### Public game presence in another experience

An optional `/presence/mcp` endpoint lets an authorized Slack, editor or browser
session inspect the same player's live game status and recent public chat.
Set a separate long random `presence_token` in this player's private config and
optionally a friendly `world_label`. Supply the endpoint as an ordinary HTTP MCP
server with `Authorization: Bearer <presence_token>`. It is also compatible with
Instance's optional installation-owned tool connections when that client has
the explicit `tools:use` grant. Keep its header in the installation's secret store.

This credential exposes only `minecraft_status` and `minecraft_recent_activity`.
It cannot start tasks, wake the controller, move, stop, or build. Original request
text, private whispers, control credentials, and raw action receipts are excluded.
Progress remains an agent report. The full game tools and their active-turn
authorization stay on the separate `/mcp` endpoint; never give its control token
to another experience as a substitute for read access.

The owner chooses which clients may see these public world observations. This
does not promote a shared Slack room into an owner-private context or make other
conversation providers visible. A remote reader still needs a trusted route to
the loopback endpoint. New work and action requests continue through the game's
existing human request and task controls.

Read-only experiment helpers require explicit player directory names:

```sh
python3 ops/observe_run.py --root /private/workshop --players builder-one builder-two --out /private/observations --once
python3 ops/analyze_experiment.py --root /private/workshop --players builder-one builder-two --briefs /private/run.json --observations /private/observations --out /private/results.json
python3 ops/watch_report.py --root /private/workshop --players builder-one builder-two --briefs /private/run.json --out /private/watch-results.json
```

For a running experiment, `ops/measure_attention.py` separates planner admissions
from provider requests, waiting decisions from active-turn advice, and quiet
waiting from hourly capacity limits. It reads the named players' user-service
journals and the observer's samples; it never prompts agents or changes game
state. This journal reader requires Linux/systemd.

```sh
python3 ops/measure_attention.py --root /private/workshop --run /private/experiment --seconds 7200
```

The experiment directory needs `briefs.json` with `started_at` (ISO timestamp),
`players` (player-directory names), and `limits.max_seconds`. If available,
`accepted_tasks` maps each player to its task `id`; this excludes a prior task's
idle state while the new request is being accepted. Run `observe_run.py` with
`--out /private/experiment/observations` for the same players. Measurement stops
no later than 15 minutes after the experiment's time limit, including on restart.

Optional `measurement-inputs.json` maps player names to read-only usage sources.
Capture baselines **before** dispatching the experiment. A native runtime entry
uses `kind: native_sqlite`, `path`, `session`, and `baseline_seq` (the session's
current maximum event sequence). A Codex entry uses `kind: codex_usage`, `path`
(its session JSONL), `session`, `baseline_offset` (current byte length), and
`baseline_totals` (the last `token_count.info.total_token_usage`). These readers
are optional measurement adapters; other ACP implementations need not expose
their internals. Without one, provider usage is reported as unavailable.

`efficiency.json` reports admission reasons, decision holds/wakes, sampled idle
intervals, provider usage and capacity waits. Native runtime events expose
model-request attempts; Codex exposes usage updates, which are not assumed to
map one-to-one to requests. Missing or failed requests are not guessed.
Cached tokens remain separate from totals;
these are not dollar estimates. A held decision is **not** automatically counted
as an avoided LLM request: that causal claim needs a suitable comparison run.

`task_work_turns` and `acp_turns_started` are separate: a read-only reply after
delivery can start an ACP turn without spending another construction turn.
Metadata-filtered evidence is counted separately from batches that did or did
not call a decision model. Eligible branches in a partly filtered batch can
still call the model, so filtered-event counts are not request savings. The
collector also retains connection permission snapshots. When journal coverage
changes, it re-reads retained journal entries from the original experiment start,
deduplicates by journal cursor, and preserves provider measurement baselines.
Entries already removed by journal retention cannot be recovered.

Reports contain private run material and belong outside the repository. A model
classification or agent-reported completion does not establish artifact quality
or a successful collaboration; inspect the world and participation separately.
Use the observer's persisted events for long-run analysis: the player's own
history retains only its latest 1000 events. Reports identify their evidence
coverage; recorder gaps or a late start can still leave missing observations.
The observer's `latest.json` includes remaining budgets and attention signals;
`attention-changes.jsonl` records changes in blockers, interruptions, disconnects,
long turns, inactivity and review needs. A legitimate evidence wait is informational,
not a stall. This recorder does not steer, retry, restart or complete agents.
Both reports include `deadline_passed` and `last_work_report` independently of
the task's current authority status. Thus a deadline can end authority while
the preceding delivery-for-review report remains inspectable. This uses the
latest task-bound structured work receipt, not chat prose or a stale review
timestamp. It never turns an agent report into independent acceptance; a later
rework report supersedes the earlier delivery report.

## Development and verification

```sh
npm test
```

The default suite uses synthetic fixtures and independent ACP processes, without
a Minecraft server or model account. CI runs it on Linux. Optional `tests/*_live.py`
scripts require an explicitly configured disposable server or model endpoint.
Some use operator RCON to prepare test terrain; do not run them against a world
you want to preserve. Their presence is not evidence that a current release has
passed live Minecraft or provider testing.

Players may still get stuck, misjudge materials, miss a waiting condition or
produce unnecessary narration. This is an experimental adapter, not a general
construction solver. Mineflayer's handling of newer item/component types also
depends on its supported server versions.

Built on [Mineflayer](https://github.com/PrismarineJS/mineflayer),
[mineflayer-pathfinder](https://github.com/PrismarineJS/mineflayer-pathfinder),
and the [Model Context Protocol SDK](https://github.com/modelcontextprotocol/typescript-sdk).
The Minecraft name and game are owned by their respective rights holders.

## Contributing

> [!NOTE]
> This project is not currently accepting external contributions, but we're actively working toward opening this up. We value community input and look forward to collaborating in the future. For now, feel free to fork and experiment!

Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit [Contributor License Agreements](https://cla.opensource.microsoft.com).

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.

### Instance-owned conversation attention

Set `conversation_attention: {"enabled": true}` to submit fresh public game chat
as audience-local facts to an endpoint advertising
`com.microsoft.amplifier.attention` v1. Set `conversation_id` to the same source
ID used by the session's context grant. Instance owns the evaluator, credentials,
uncertainty preference, deduplication and budgets. The adapter rechecks the source
snapshot and uses a one-use offer with the next ordinary ACP prompt. Provider
configuration in `decision_attention` is **not** used for social participation;
that older configuration still serves separately commissioned domain-condition
watches/assessments. A migration must remove the old `participate` helper path.

Human questions to the room and implicit follow-ups can now be considered without
matching a name. Public evidence excludes whispers and private `/task` management
briefs, including older Operator records without provenance. New chat records
carry transport-assigned provenance; a real game player named Operator remains
eligible. The same public-chat boundary applies to attention candidates, context
messages, participants derived from messages, presence and task-condition watch
evidence. Private control briefs retain their local authorization path; shared
context exports include task summaries rather than original requests or nested
private observations, and project action receipts without their raw inputs or
results. Peer exchange
budgets, the human-activity window, Stop, action leases and task deadlines still
apply. Without the host capability, this opt-in mode uses bounded ordinary ACP
response opportunities; it does not claim cheap pre-LLM filtering. Disable the
mode to retain legacy directed-message routing. No model call is made merely
because the world is idle.

Offers queued in the body are not admitted ACP turns. Expired, disconnected or
used offers cannot be reused; interruption can lose an opportunity and does not
authorize replay. The next fresh message provides a new opportunity. Game action
permissions are still checked independently. Streaming ACP text is received by
the client; final replies remain bounded game messages, and explicit chat tools
can deliver intentional progress during work. Raw reasoning/tool output is not
broadcast.

Known closed ACP transports reconnect and load the saved session before either
an attention request or ordinary turn reservation. A failed reload preserves
queued input and planner allowance. Disconnects after a prompt starts remain
interrupted and are not automatically replayed. Planner capacity waits retain the
separate bounded task-watch observation described above.

Participation diagnostics distinguish source fetch, host evaluation, offer
validation and local delivery. Local delivery rejections report a bounded HTTP
status and a fixed reason code (for example `source_changed`, `inbox_full`,
`peer_budget_exhausted` or `peer_window_expired`). Unknown responses remain
`unknown`; logs do not include raw error bodies, credentials or conversation
text. Host reasons use a fixed diagnostic vocabulary; event IDs and source
signatures are logged only as fingerprints. An evaluation request, a queued
offer and an admitted ACP turn are separate events and must not be counted
interchangeably.

Before requesting evaluation, the adapter checks the body's current inbox and
existing peer delivery limits. These are transport admission/capacity checks;
the adapter does not classify relevance, choose engage/hold, or call a decision
provider. While local delivery is blocked, it retains fresh pending
evidence and checks those local facts without calling an evaluator. The body
rechecks them on delivery; preflight is not permission. Other failures back off
an unchanged proposal for 10, 20, 40, 80, then at most 120 seconds. Changed source
evidence is eligible immediately, and cleared local constraints are rechecked
without renewing any task. Each retry fetches current pending evidence and asks
Instance for a new result, preserving the source's original trigger and timestamp.
Instance can return `hold/duplicate`; the adapter honors it. Expired offers are
discarded, and no rejected offer is cached or replayed. Existing pending-message
expiration and task budgets remain unchanged.

A timeout, malformed delivery reply or unrecognized failure leaves the delivery
outcome `unknown` and `queued: null`, rather than claiming rejection or success.
The next attempt reads pending source facts again. The body revalidates and
consumes the pending message IDs together with saving the inbox, so a delayed
duplicate request or retained snapshot cannot accept those messages again,
including after reload. An already accepted message remains in the existing
inbox path; it is not posted again. A fresh unrelated message remains eligible.
This protects local queue admission, not exactly-once ACP execution or game
effects: interrupted prompts still require receipt-based inspection and are
never replayed by this retry mechanism.


### Active-turn conversation and resource freshness

Background responsibility watches receive `environment:crops` observations of
loaded crop and farmland blocks within 16 blocks of the player, capped at 64.
These include server-observed growth age and soil moisture, with explicit limited
coverage. The adapter reads existing chunk data without moving, growing crops,
starting a planner, or spending an action. Unchanged observations retain stable
content so the watch layer can skip repeated evaluation. Crop growth can now
satisfy an agent's own waiting condition; the agent still chooses whether and
how to harvest under its existing task limits.

Public human and peer messages can now reach an already running ACP prompt.
The adapter negotiates Instance's optional active-only awareness capability
(`inputContinuity.awareness` v1), then uses `_session/steering` with a stable
`inputId`, the current `activePromptId`, `intent: awareness` and
`idleBehavior: promptRequired`. This updates context; it does not create a
prompt, consume a queued attention opportunity, authorize another task, or
extend a deadline. Instance still owns engage/hold evaluation. The same path is
used for any backend advertising that capability; the adapter does not identify
or special-case native versus Codex engines.

The ACP transport has one reader, routing concurrent replies by request ID while
retaining notification order. A private `awareness-receipts.json` journal records
source IDs, prompt binding, delivery and incorporation states, without copying
message bodies. At most 16 batches of 16 recent public messages are submitted per
turn. Whispers, private Operator briefs and raw action receipts never enter this
projection. Unknown delivery is not retried; a receipt query may establish later
incorporation only when the endpoint separately advertises
`_meta.steering.receiptsMethod: "_session/input_receipts"`. Steering alone does
not promise that native Runtime extension. Without it, the journal retains the
delivery acknowledgment and reports receipt coverage as `unsupported`; it does
not claim incorporation, probe unknown methods, or replay the input. Receipt
failure or an unreadable journal does not authorize replay.
Late input remains history and follows ordinary attention/inbox handling.

A generic ACP endpoint need not implement steering. It receives new public
context through MCP results and ordinary subsequent turns. Only changes are
appended to tool results, avoiding repeated copies of an unchanged chat history.
The `conversation` tool can explicitly read the recent bounded public context.
No model is polled to discover messages. Injected context can cause additional
model work inside the existing prompt: steering receipts are **not** model
request counts or proof of cost savings.

Before `chat`, `tell` or `give`, use the latest public context `revision` as
`conversation_revision`; read `conversation` to refresh it. A stale cancellation
or report is rejected before sending, just like a stale item handoff. Before a `container` deposit/withdrawal, also inspect
that container and supply its `contents_revision`. The body rechecks public
context immediately before delivery, including after asynchronous preparation;
containers compare a fresh server contents fingerprint before the first click.
A changed plan or contents fails with an actionable refresh message. A completed
transfer stays completed: later corrections do not undo it or justify repeating
it. Ambiguous or partial transfers still require inventory/container inspection.
These are bounded checks, not locks on another player or globally atomic state.
Content fingerprints detect changed contents, not every intervening edit that
returns to identical contents.

Automatic final replies are fenced against the public-context revision exposed
at prompt start, supplied in a tool result, or explicitly reported incorporated
by the endpoint. A newer unseen message suppresses that stale final; it does not
launch an extra unbudgeted prompt. Ordinary source attention remains available.
A message arriving after the final check is outside that check's cutoff. Tool
context exposure means supplied evidence, not proof the model understood it.

Identified ACP text is collected per `messageId` in first-observed nonempty text order.
The latest nonempty, non-commentary message is selected with all of its chunks;
a delayed older chunk cannot overwrite it. Both `messageId` and
`_meta["com.microsoft.amplifier.message"].phase` are optional on each
`session/update`'s `update` object. Recognized phases are `commentary` and
`final_answer`; omitted phases retain an existing message's classification.
Empty text envelopes (including steering receipts without a `messageId`) do not
create a message, change its phase/order, consume a tool separator, or trigger
text callbacks. Receipt retrieval remains independent. An empty new message is
not a withdrawal of an earlier answer. An explicit
nonempty revised answer (including a structured pass decision where used) takes
precedence over older messages. A turn containing only commentary or empty text
has no final text to broadcast.

Unidentified endpoints retain append behavior, including text before and after
tools; they cannot provide the same revision guarantees. A new ID does not mark
an earlier message complete. Tool state and media are independent of text
selection, and changing IDs does not discard them. Raw reasoning and tool
details are never broadcast as final chat. See the shared
[collaboration contract](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/collaboration.v1-candidate.md#answer-identity-and-revisions).

### Farming and movement repair

`gather(block, targets, count)` mines an explicit ordered list of 1–8 unique
coordinates, within 24 blocks of the player's starting position. `count` defaults
to one and cannot exceed the list length. Use `find`, `map`, `inspect` and public
conversation to select a resource site first. A block's type does not distinguish
natural stone or timber from another player's paving, walls or posts. Selection
is the agent's responsibility; the adapter does not claim to know block ownership.

Gathering never searches for a substitute. It stops on a changed, unloaded,
unsafe or unreachable target, and rechecks the target after walking and equipping
a tool. Results list exact removed coordinates and observed replacement blocks,
with inventory deltas summed across stacks. An unconfirmed removal stops the
batch without a retry. The old name/count-only call is refused before movement or
digging; callers must supply `targets`. Ordinary movement, footing, harvesting,
Stop and task-budget checks still apply. This is a Minecraft tool contract; ACP
and Instance attention are unchanged.

`till(x,y,z,expected)` uses one inventory hoe on an expected grass/dirt block
within clear reach. It verifies air above, the held hoe and the target after
aiming, and accepts only a matching server farmland update as success. It does
not walk, clear obstacles, plant, hydrate or retry an unconfirmed interaction.
Coarse/rooted dirt are intentionally excluded. The modern Java block-interaction
packet is sent after the cancellation recheck; this avoids Mineflayer's hidden
await between aiming and interaction. Ordinary player/server restrictions still
apply. `tests/farming_live.py` is an optional no-model check against a
loopback-only disposable `level-name=farming-fixture` server; it creates test
supplies and must never target a shared world.

Recognized movement/digging guards now include observed feet/head/floor geometry,
a fixed reason code, repeated-failure count for the same local observation and
specific repair suggestions. Changed arguments or observed geometry reset that
repetition signal. Bounded collision observations across the player's footprint
identify current support contacts and body obstructions, including adjacent
slabs and tall fence shapes that the center cell misses. Unloaded cells and
missing shape data remain unknown. These contacts do not establish what caused
earlier movement or prove a route safe. Unknown failures remain unknown. Diagnostics never remove
blocks, retry movement, relax walk-only constraints or bypass player-footing
protection; the agent chooses the next permitted approach.

Upgrade the body and controller together at a coordinated idle boundary. Preserve
installation state, sessions, accepted work and budgets. Installing these tools
is not permission to renew or resume a stopped task. Synthetic protocol and body
regressions run in the normal suite; their success is not evidence of a live
native/Codex provider run or a production-world rollout.


## Healthy work, action leases and ACP lifecycle

A planner turn has no implicit elapsed-time cutoff. Standard ACP `session/prompt`
settles only on its matching response, protocol/transport failure, or cancellation
following revoked local authority. Long reasoning or compaction is not a failed
connection. The client advertises standard `clientCapabilities.session.compaction`
and records typed `compaction_update` statuses; a completed compaction does not
complete a prompt. Endpoints without these updates remain usable. After 180
seconds without new text or a tool/compaction status transition, private telemetry
reports `planner_progress_unknown`. This is neither a provider-health claim nor
an automatic retry/cancellation. Empty metadata, repeated status and usage updates
are not progress evidence. No provider-specific SDK or invented heartbeat is used.

The authenticated body `/turn` response includes `action_lease` version 1. New
controllers opt in with `renewable_lease: true`, then renew every 30 seconds at
`/turn/renew` with the exact `lease_id` and `task_id`. A lease lasts at most 240
seconds, and never past the bound assignment deadline. Renewal requires the same
live turn, same task identity/deadline/cap/consumed count, and a running assignment.
It does not reserve another turn, replenish the 24-action allowance, alter the
hourly pacing limit, or change any durable task field. Stale, expired, stopped,
replaced, or exhausted assignments cannot be resurrected. An accepted task created
within a conversation can bind the current lease; an unassigned conversation or
legacy controller has a nonrenewable 240-second action window. The controller and
body must be upgraded together at idle; older bodies do not provide this contract.

A body timer closes an abandoned lease and cancels physical activity even when no
controller polls it. Each mutating operation separately retains its 60-second
limit, shortened to the current lease boundary when necessary; renewing a lease
does not extend an already running operation's deadline. Human Stop, disconnect,
and assignment expiry remain authoritative. A failed renewal/control request is
ambiguous and closes the controller's current work path; it is not retried as a
new prompt or new turn. Cancellation acknowledgement is not effect settlement.
Full action receipts and uncertain outcomes remain available for review.

Provider connection/inactivity/retry policy belongs to the runtime. Any future
Instance maintenance extension must be negotiated before use. In particular this
adapter does not send `/compact` through a decorated prompt and claim tool-free
maintenance, nor does it infer receipt lookup support from steering alone.

The planner's stable experience instructions refer to MCP tool descriptions for
mechanics instead of duplicating that manual in every user message. Fresh world,
request, assignment, attention and uncertainty fields are still passed intact.
This reduces instruction bytes, not an asserted token/cost saving or a semantic
compaction of owner evidence. More extensive context-snapshot integration awaits
an explicitly negotiated Instance/runtime contract.
