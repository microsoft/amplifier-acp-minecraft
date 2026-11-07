# Server and ACP player setup guide

Use this with the [server-setup skill](../skills/minecraft-server-setup/SKILL.md).
The workflow applies to a new installation or an existing server; it does not
require Constellation, a particular provider, a shared provisioning service, or a
custom world mod. Read only the sections relevant to the requested operation.

## 1. Establish the actual installation

Before reusing an example, inventory:

| Area | What to establish |
| --- | --- |
| World | Host, owner, Java server distribution/version, world path, backups, player accounts and allowlist |
| Human access | Java gateway, Bedrock gateway if any, LAN/VPN routes and intended exposure |
| Agent access | Authenticated Java login or strictly isolated trusted proxy, configured peer names |
| Each player | Private home, identity, ACP engine/family, original session/binding, control port/token, current authority and unfinished effects |
| Services | Actual body/controller/gateway/backend units or process commands and prior active/masked state |
| Updates | Enrolled provider/participant, current transaction/gate, source/SDK/artifact provenance and schedule policy |

Use current state and matching receipts, not a stale staging message. Do not infer
that another host is updated because it shares a display name. Preserve existing
choices unless the request changes them. For a fresh server establish the host,
world/version and approved access; obtain the owner's required account and server
license/EULA acceptance through the normal official flow. Never invent credentials.

## 2. Create or reuse the Java world and gateways

For an existing world, keep its world path, seed, spawn, structures, resources,
player UUIDs, inventory and account links. Take an appropriate backup before
server changes; do not copy an actively mutating world and call it a verified
backup. Use the server's documented save/backup procedure or a coordinated stop.
An adapter-only update does not normally require stopping the world.

For a fresh world, obtain the chosen server and compatible Java runtime from their
authoritative sources; pin versions and record artifact hashes. Do not download
an arbitrary latest plugin into a running installation. Allocate persistent
owner-controlled data and explicit service commands/restart behavior. Configure
server access and allowlisting before exposing it.

The adapter defaults to Java **1.21.1**. The tested newer-server arrangement uses
**Paper 26.3 + ViaVersion/ViaBackwards**, while the Mineflayer body remains configured
as 1.21.1. Translation does not give the agent native knowledge of newer recipes
or blocks. Retain inventory/barrier/placement checks and validate new mechanics
separately; don't disable them to hide translation errors.

Keep human and trusted-agent access distinct:

- Human Java players use authenticated Java access and their ordinary licensed
  accounts. Bedrock users need the [Geyser/Floodgate gateway](xbox-lan.md).
- Agent players can use individually licensed Microsoft-authenticated Minecraft
  accounts, or an owner-controlled offline agent proxy restricted to trusted local
  routes. An offline name does not authenticate a human and must not be exposed as
  a public human endpoint.
- Keep backend forwarding secrets and proxy-to-server routes private. Do not make
  the backend broadly reachable just because the front gateway authenticates.
- For remote agents, use a dedicated approved private route to their game endpoint;
  do not substitute a public human port. Ports in examples are not universal.

Use [Xbox LAN setup](xbox-lan.md) for NetherNet, discovery/firewall/ICE, authentication,
the temporary version-specific compatibility option and real console validation. A separate human
gateway permits that repair without restarting the world or agents.

### Preserve the same player across Java and Xbox

A successful Bedrock login does **not** establish a Java account link. Without one,
Floodgate assigns a separate Bedrock UUID; the player may appear at spawn with an
empty inventory even though their original Java save is intact. Verify account
identity separately from discovery and transport.

Follow [Floodgate account linking](https://geysermc.org/wiki/floodgate/linking/).
Global linking uses the official linking service; local linking is scoped to this
server/proxy. A local database entry takes precedence over global linking. For
local SQLite linking, install the compatible `floodgate-sqlite-database.jar` in
**the proxy's Floodgate plugin directory**, enable `player-link.enabled` and
`enable-own-linking`, and select `type: sqlite`. Those configuration flags alone
do not install the extension or create a verified account link.

Use the normal two-account linking flow, or an explicitly authorized migration of
an already authenticated mapping. Never infer ownership from similar names or
remove the username prefix as a substitute for linking. Before a migration, record
the authenticated Xbox identity/XUID and Java UUID, back up existing link records
and both players' saved data at a settled boundary, and preserve unrelated links.
Do not copy one player's inventory over the other. Restart only the affected
gateway if needed, then have the human reconnect: check the resulting Java UUID,
location and inventory. Keep newly created Bedrock data available for deliberate
recovery; linking does not merge it into the Java inventory.

**Version compatibility:** the tested Floodgate SQLite extension 2.2.5 build 138
uses `javax.inject`; the tested Velocity 4.3.1/Guice 7 path required `jakarta.inject`
for database injection. Our installed extension used a narrowly reviewed annotation
compatibility rebuild. Do not assume the official database download works merely
because Floodgate itself starts. Prefer an upstream-compatible build when available;
otherwise review/test that exact compatibility change and record its source and
artifact hashes before installation. Check initialization errors and a real linked
login. This is separate from the temporary Xbox LAN workaround.

## 3. Stage one self-contained player

Requirements: **Node 22+**, **Python 3.12+**, a compatible Java server, and a separately
authenticated ACP engine supporting HTTP MCP. Use reviewed repository source:

```sh
git clone https://github.com/microsoft/amplifier-acp-minecraft.git
cd amplifier-acp-minecraft
npm ci --ignore-scripts
python3 -m venv .venv
.venv/bin/python -m pip install --force-reinstall -r requirements.txt
```

For production updates stage a separate source/dependency environment; don't
replace dependencies beneath a running controller. See [installation updates](../INSTALLATION-UPDATES-DESIGN.md).
The official SDK is pinned by immutable upstream commit in `requirements.txt`.
Verify its installed distribution's `direct_url.json`, not `0.12.1` alone; consult
[the SDK guide](python-sdk.md) for the exact supported revision and wrappers.

Copy [config.example.json](../config.example.json) and
[endpoint.example.json](../endpoint.example.json) into a private installation
home. Keep the directory 0700 and sensitive files 0600. Set:

- A unique player identity/name, chosen Java authentication and correct server route.
- An unused loopback control/MCP port and a strong random control token.
- The separately authenticated ACP command, working directory and installation-local
  Python interpreter; use the engine's normal credential flow, not someone else's
  copied session or tokens.
- Current public **agent peer names**, including agents on other engines. Otherwise
  peer speech can be mistaken for human authority. Preserve the server's actual
  UUID/source attribution; never infer human identity from message text.
- Explicit behavior policies appropriate to this request (next section).

Each additional player has its own home, credentials, session and port. Reusing a
name, token or directory is not a shortcut to a separate installation. Preserve
existing portraits/skins during upgrades; use the [skin skill](../skills/minecraft-agent-skins/SKILL.md)
for requested appearance work.

### Context/MCP routes and no-start staging

The body requires a bearer token and rejects browser-origin control. Loopback is
relative to the **connecting process/container**, not the administrator's laptop.
A remote or containerized ACP engine needs its own approved route to this body's
MCP/context port. Do not expose a shared host control network or another agent's
credentials to solve a missing route.

For no-start staging, write private pending configuration and leave services
inactive. Do not register a dead context provider with an otherwise live Instance;
it can break unrelated Slack `session/new` before inference. Once the body is
ready, inspect actual provider metadata, test HTTP/MCP/context reachability from
the engine/Instance namespace, then register/read back the intended provider using
its authenticated supported interface. Existing connected upgrades retain their
registration. A local status label is not route or registration evidence.

The optional [context registration helper](../ops/register_context.py) is an
operator tool, not a universal enrollment service. Inspect its current options
and the actual installation before use. Plain ACP can receive MCP configuration
at standard session setup without an Instance-specific context API.

## 4. Choose behavior explicitly

Installation, code updates and game login grant no construction authority. Keep
old tasks, limits, consumed counts, unknown inputs and stopped/expired status
unchanged. An initial `incoming_chat_only: true` installation is useful for
bringing up real conversation without silently resuming construction.

| Requested behavior | Policy/reference |
| --- | --- |
| Conversation only | Keep intake disabled; verify the effective advertised mode |
| Natural human task acceptance/amendment | Explicit `human_task_intake.enabled`; [intake](human-task-intake.md) |
| Direct human responsiveness and fewer artificial action pauses | Explicit `human_engagement.enabled`; [human-led play](human-led-play.md) |
| Greetings/help from observed activity | Explicit `human_engagement.activity_scope: conversation_only`, negotiated host attention activity support; movement/interaction facts are not commands |
| Completion-bound new work | Explicit default-bound policy plus independently discovered helper-v2 support; [bounds](completion-bound-tasks.md) |
| Independently accepted helper work | Explicit delegation policy and original human provenance; [delegation](human-led-play.md#independently-accepted-helper-work) |

`incoming_chat_only` is an installation policy, not an hourly-capacity condition.
Waiting or raising a quota cannot fix disabled task intake. Inspect effective
`task_capabilities` and blocked reasons before claiming the agent can act.
Source updates never enable these opt-ins by themselves. Honor explicit human
Stop/limits and actual host/provider/tool constraints. Restrictive amendments
can exhaust future authority without rewriting work already consumed.

Helpers are optional **pure decision executables**, separate from the selected ACP
engine. Discover `helper-capabilities` before using tagged finite/no-configured-bound
watch/continuation schemas. Do not substitute huge numeric sentinels or install a
native engine to give a third-party agent a helper. Unknown capability is not support.
Optional Instance attention/steering/receipts are separately negotiated; keep vanilla
ACP fallback and retain unknown delivery without replay.

## 5. Start and verify in layers

For manual local operation from the reviewed source directory:

```sh
node body.cjs /absolute/player-home/config.json
.venv/bin/python adapter.py --home /absolute/player-home
```

These run in separate terminals. Optional Linux user-unit templates are
[body](../ops/minecraft-body@.service) and
[controller](../ops/minecraft-agent@.service); adapt their absolute paths and the
installation's Python environment before enabling. Other operating systems need
their own supervisor. Do not assume systemd or install its Linux lifecycle driver
on a different OS.

Validate independently:

1. Body joins the intended world as the intended identity; authenticated read-only
   state shows actual readiness, position/inventory and tool schema.
2. MCP/context works from the actual engine namespace and provider metadata matches.
3. ACP initializes through the installed official SDK. For an upgrade, load the
   **original** saved session and require its terminal success. Saved-session replay
   can take tens of seconds; distinguish progressing replay from inactivity and
   use the documented bounded verification budget. Never replace or prime a used
   session to make health checks pass. With no saved session, initialize only.
4. Retained authority, accounting, pending/unknown receipts and world observations
   match across the change. A restore returns only the services that were active
   before it; do not remove unrelated masks.
5. A real human sends a fresh greeting and, if authorized, a fresh task request.
   Check source receipt, acceptance, actual planner execution and action results
   separately. Never inject a fake human event or replay an earlier failed request.
6. If providing console access, observe a real authenticated join. A LAN advertisement
   and transport handshake are useful independent checks, not a console result.

Mechanical fixtures may create blocks/resources, so run them only against their
explicit disposable worlds. No operator builds, teleportation, supplies or unrelated
missions belong in a production verification. See [development checks](adapter-reference.md#development-and-verification).

## 6. Updates, recovery and handoff

Use the [installation-owned update participant/provider](../INSTALLATION-UPDATES-DESIGN.md)
for supported Linux installations. It stages exact source/SDK dependencies, gates
new admission, waits for settled work, preserves authority/unknown effects,
verifies original-session compatibility and restores captured services. Its
reference-aware retention keeps rollback/uncertain transaction material while
pruning regenerable abandoned stages. Preserve the fixed host-owned helper layer
and separately enrolled pure task-helper path.

Enroll schedules/agent-initiated updates only when requested; hourly `when_idle`
is an explicit policy, not implied by installing code. The same participant must
run for shared Instance/runtime/engine/container updates that affect the player.
A source provider does **not** automatically update Java worlds, gateways, skins,
container OS packages or local model files unless separately enrolled and authorized.
Use fresh coordination for those components, not a completed historical hold.

On failure, inspect durable effects and the exact transaction/session state before
resuming. Roll back code/configuration only as justified; never restore old task
files to erase consumed counts or make continuity pass. Unknown accepted input is
not replayable. Before listener restoration, code rollback may be appropriate;
after verified restoration has begun, follow the updater's restore-only recovery.

Keep a private final receipt: source/dependency hashes, services/routes, policies
actually enabled, original-session/task/world continuity, actual human tests and
unverified aspects. Give the user a short result and only the remaining actions
that require their access. Improve the relevant guide/helper when a reproducible
new lesson appears; do not put private installation details in the repository.
