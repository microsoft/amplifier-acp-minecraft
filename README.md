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

Join your server through Minecraft's Multiplayer screen and address a configured
player, for example `BuilderOne, help design a bridge.` Group prefixes such as
`Team,` address all configured agents. After a direct address, that human's
follow-ups continue to the same player for ten minutes. Addressing a different
player transfers conversational focus. Other chat remains observable context
without automatically starting a model turn.

Explicit requests from configured peers can start bounded turns. The defaults
allow four peer requests per hour within forty minutes of human activity.
`tell(player, text, intent)` makes the recipient explicit. `intent=request` asks
for action; `update` and `ack` add visible FYI/ACK markers and remain context
without waking the recipient. This is a public chat convention, not a hidden
coordination channel or an ACP extension. Configure `aliases` consistently on
all players when using shorter names. Private whispers are excluded from shared
context; replies from this adapter currently appear publicly.

The tools cover observation, terrain maps, route planning, movement, following,
gathering, digging, crafting, inventory, containers, furnaces, placement, small
build patterns, signs, item handoffs, chat and Stop. Physics and movement run
without model calls. Agent tools expose no arbitrary shell, RCON, teleport or
item creation. Operator-only RCON helpers live under `ops/`.

Movement verifies arrival height and reports obstruction or stalled progress.
The body's vanilla player collision width matches Minecraft's float dimensions;
this prevents edge-overlap corrections during sprint-jumps onto full blocks.
It does not relax server collision checks or grant new movement capabilities.
For level activities that prohibit jumping, select `mode: "walk_only"` for both
`plan_route` and `move`; ordinary pathfinding permits other traversal strategies.
Digging checks footing and adjacent liquids. Crafting and placement refresh the
server inventory. Sign writes verify the server's text echo and can reject stale
edits with `expected_lines`. Item drops remain physical world interactions:
another nearby player may collect them, so verify the recipient's inventory.

`tests/movement_live.py --node /path/to/node --properties /path/to/server.properties
--out /path/to/results.json` checks climbs, descents and blocked head clearance
through the body against a loopback-only disposable `movement-fixture` or
`container-fixture` world. Use `--port` for its translation proxy. The fixture
creates test geometry and must never target a shared world. It uses no model.

`container` inspects ordinary chests (single/double) and barrels, or deposits and
withdraws 1–64 ordinary supply items. It checks reach without moving, uses
server-confirmed clicks, and verifies the exact source and destination deltas.
Insufficient supplies or capacity fail before transferring. Shared containers
are not locked: coordinate ownership, and inspect after a partial or unconfirmed
result instead of repeating it. An interrupted transfer can leave a cursor;
`recover` returns it to its original source slot when safe. It never drops
leftovers to make room. Custom-name, enchantment, and other component-bearing
items require more precise selection and are currently refused.

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

Each turn permits at most 24 mutating calls over 220 seconds; builds and gathers
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
actual action receipts, presence and task status discoverable through an
authorized context layer. It uses a separate `context_token` and a non-owner game
audience grant. Private owner conversations do not become visible to the game.
The history is bounded and reports its coverage. Standard ACP does not itself
merge conversations or authorize cross-surface retrieval.

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
private observations. Peer exchange
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
