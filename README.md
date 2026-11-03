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
For level activities that prohibit jumping, select `mode: "walk_only"` for both
`plan_route` and `move`; ordinary pathfinding permits other traversal strategies.
Digging checks footing and adjacent liquids. Crafting and placement refresh the
server inventory. Sign writes verify the server's text echo and can reject stale
edits with `expected_lines`. Item drops remain physical world interactions:
another nearby player may collect them, so verify the recipient's inventory.

## Continuing tasks and recovery

A routed human request can authorize `work_begin`. The agent reports progress
with `work_report`, choosing running, waiting, blocked, or review. Defaults are
12 model turns and 40 minutes per task, with 30 model turns per player per hour.
The hourly limit defers further calls without consuming queued messages or
renewing the task's deadline. State survives controller restarts.

Stop cancels work and revokes the current action lease. Interrupted work requires
inspection. Clean model turn limits can continue only when tools have settled and
the body is idle, within the existing task budget. `review` means the agent has
reported completion; it is not independent verification of the world.

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
and `/resume-reviewed`, `/continuation`. POST `/mcp` serves the scoped game tools. `/inbox` consumes
messages and is reserved for the single controller; observers use `/state`.
Control credentials stay in the private installation.

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

See the runtime's [assessment](https://github.com/microsoft/amplifier-constellation-runtime/blob/main/docs/assessment.md)
and [watch](https://github.com/microsoft/amplifier-constellation-runtime/blob/main/docs/watches.md)
contracts. Disabling these optional helpers leaves ordinary ACP operation available.

Read-only experiment helpers require explicit player directory names:

```sh
python3 ops/observe_run.py --root /private/workshop --players builder-one builder-two --out /private/observations --once
python3 ops/analyze_experiment.py --root /private/workshop --players builder-one builder-two --briefs /private/run.json --observations /private/observations --out /private/results.json
python3 ops/watch_report.py --root /private/workshop --players builder-one builder-two --briefs /private/run.json --out /private/watch-results.json
```

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
