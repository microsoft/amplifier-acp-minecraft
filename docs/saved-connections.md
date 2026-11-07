# Saved Minecraft connections

The optional installation-owned connection command implements the shared
service-connections v1 contract. It lets a host UI disconnect a player while
retaining the connection, then reconnect it later. This is separate from task
intake: connecting neither renews expired work nor replays earlier requests.
The matching shared host/API implementation must be present before enrollment;
an installed Minecraft source revision alone does not add UI controls.

## Enroll an existing connection

Each connection needs its own home, context provider, control port, game route,
session, credentials and two Linux systemd user units. Follow the
[setup guide](server-setup.md) first. Do not point a second saved connection at
another world's home or clone its task/session state.

Add an explicit descriptor to that connection's owner updater configuration:

```json
{
  "service_connection": {
    "id": "minecraft-visit",
    "label": "Workshop visit",
    "revision": "<64 lowercase hexadecimal characters identifying the owner configuration>",
    "context_provider_ids": ["minecraft:example:visit"]
  }
}
```

Use a stable digest of the reviewed connection configuration as its revision.
Change it when the connection definition changes, never during a pending
operation. The descriptor's context provider must match the registered private
context/MCP route. Preserve existing providers' `enabled` fields when updating
their registration.

Install the existing updater helper set together with `connection_state.py`,
`installation_connection.py` and `connection_session_job.py` in the stable
owner helper directory. In particular, the new updater participant imports
`connection_state.py` even when connection controls are not enrolled. Keep the
whole helper set at one reviewed revision; do not refresh individual imports.
The installed body also needs `connection-state.cjs` from the same source.

Run `installation_enrollment.py` as described in the
[updater guide](../INSTALLATION-UPDATES-DESIGN.md). Its optional
`service_connections` delta contains fixed status/connect/disconnect argv.
Merge through the host's enrollment interface without removing other
components, participants or connections. The browser supplies only the saved
connection ID, revision, action and request UUID. It supplies no executable,
path, secret or command arguments. This command is not an agent MCP tool.

The updater delta advertises existing connections only. To offer a working Add
form, separately enroll the prepared-choice provider below. A documentation
link is not an interactive setup flow.

## Add from prepared server choices

`installation_connection_add.py` implements the optional typed Add contract.
It saves a new connection from an **unused, separately prepared installation**.
It does not provision arbitrary destinations supplied by a browser. Prepare one
slot per available connection using the setup guide: its own home, source,
pinned SDK environment, identity/endpoint, private game route, registered own
context/MCP route and installed but inactive, disabled systemd units. Keep the
prepared context provider explicitly `enabled: false` until its saved connection
has been reported to Instance with a closed per-connection gate; an enabled dead
provider can break unrelated conversations. Preserve
any existing server player data. Do not clone used sessions or tasks to make a
slot. Its domain state must have no task, turn, active sequence or saved session;
use `incoming_chat_only: true` with human task intake disabled.

Install this Add helper with the complete connection/updater helper set outside
agent-writable mounts. Create a private owner template (mode 0600):

```json
{
  "schema": 1,
  "state": "/owner/minecraft-add",
  "agent_home": "/owner/agent-instance/example",
  "helpers": "/owner/minecraft-helpers",
  "python": "/owner/helper-venv/bin/python",
  "slots": [{
    "id": "visit",
    "label": "Workshop",
    "config": "/owner/prepared-visit.json",
    "config_sha256": "<SHA256 of that connection's owner configuration>",
    "route_receipt": "/owner/visit-route-ready.json",
    "route_sha256": "<SHA256 of the route receipt>"
  }]
}
```

The connection configuration uses the same `home`, `state`, `app`, `venv` and
`units` fields as the lifecycle driver. Its state directory must be separate
from the Add state directory. The owner records route checks after verifying
the approved game route and the context/MCP route from the actual engine's
namespace. The receipt has this shape:

```json
{
  "schema": 1,
  "home": "/owner/game/example-visit",
  "checked_at": "<original check time>",
  "config_sha256": "<SHA256 of home/config.json>",
  "endpoint_sha256": "<SHA256 of home/endpoint.json>",
  "game": {"host": "127.0.0.1", "port": 25571, "verified": true},
  "context": {
    "provider_id": "minecraft:example:visit",
    "url": "http://127.0.0.1:45846",
    "secret_ref": "<registered secret reference, not the secret>",
    "runtime_namespace_verified": true
  },
  "configuration_files": {"/owner/private-route-config": "<SHA256>"}
}
```

Those ports are illustrative, not universal endpoints. In particular, a human
gateway is not an offline agent route. Never invent namespace verification
because a host port responds. Add checks this original owner evidence, the
unchanged configuration files and the actual Instance provider registration.
It does **not** claim a fresh runtime-namespace reachability test while the
body is stopped. Missing, prematurely enabled or changed registration prevents
saving. After Add settles, the setup owner confirms the mapped connection is
reported disconnected with its context gate closed, then explicitly enables
only that prepared provider through the supported registration API/read-back.
Do not enable a provider against a host without the matching connection gate.
This one-time setup step is separate from Add and never overrides a deliberately
disabled existing connection. Connect remains pending without starting services
until the exact provider metadata and enabled state match; it then checks the
live body and initializes the actual ACP endpoint.

Run the installed helper with `--config /owner/add-template.json enrollment`.
It prints one service descriptor with a revision bound to that template, a
bounded name field, authorized server choices, and fixed Add/status commands.
Enroll that descriptor in the host's `service_connections.services` catalog,
preserving existing connections, components and participants. Do not change
the template during a pending operation. Browser data cannot supply addresses,
credentials, paths or executables.

Add checks the slot is unused and stopped, journals the request, then saves
its configuration and offline admission state. The shared host alone appends
the returned connection descriptor. Lost replies resume that same file-only
save through status; changed request values or a conflicting slot are refused.
No service starts, Instance writes, session creation, task grant, work replay
or updater enrollment occur. Choose Connect separately to join. A saved slot
cannot be reused for another connection; prepare another independent slot if
needed. Updater enrollment remains a distinct owner operation.

## Settlement and preservation

- Disconnect closes game admission, waits for the current controller turn,
  action lease, sequence and inventory to settle, captures continuity, then
  stops the controller. Its `context_quiesced` report lets the host close the
  context gate only after active work settles; after the report is acknowledged,
  a later status call stops the body. It retains all saved work and unit settings.
  Offline intent also prevents an ordinary body restart from rejoining.
- Connect starts the body under closed admission. The matching `context_ready`
  report lets the host reopen only the mapped context route. The host must
  acknowledge that report before another status call advances verification.
- A separate bounded child uses the installed official Python ACP SDK to
  initialize and load the original saved session. An unused installation gets
  initialize only. There is no session/new, prompt, maintenance or synthetic
  human input. Verification allows 180 seconds total and 30 seconds without
  progress; each host command remains bounded to 30 seconds.
- Only successful session and world continuity checks release the controller.
  The final connected observation also requires the game body to report ready.
  Changed inventory, position, authority, binding or uncertain effects are not
  overwritten to make verification pass. Independent service masks remain in
  force.
- A finite task may expire while offline. Reconnect accepts the body's existing
  status-only change to `budget_exhausted` once the original deadline has elapsed.
  The private receipt records that exception against the captured full-state
  hashes. Identity, source, deadline, consumed counts, progress, waits, recovery
  and unknown receipts must remain identical. No renewal is needed to reconnect
  for chat, and the expired work is not reopened. Missing/contradictory bounds,
  early closure, arbitrary completion and other state changes still fail closed.
- Each action/revision/request is durably journaled before effects. After a lost
  reply, the host uses status only. Status may advance the same accepted
  operation; it never invents a replacement operation or repeats an uncertain
  service dispatch. Unknown settlement remains visible and requires owner
  investigation. A confirmed verification failure returns a settled failed
  result only after disconnecting safely. A correlated SDK rejection of
  initialize/original-session load is distinguishable from timeout, transport
  loss or malformed evidence; those uncertain outcomes stay unknown with
  admission closed. A settled failed request retains its receipt and never
  retries itself. The user may explicitly submit a new request with a new ID.
  A busy Add preflight stays pending; a known refused Add has no connection
  descriptor and leaves its prepared slot unchanged.

The connection driver and updater share the installation lock. An update
already in progress finishes first. While disconnected, participants defer
updates requiring saved-session verification rather than temporarily joining
the game or claiming an unperformed compatibility check. Other connected
services remain independent, but a shared engine update that includes this
participant can consequently wait until the owner explicitly reconnects it.

## Verification

The disposable tests cover interrupted dispatch, lost acknowledgments, status
recovery, preserved task/session state, active work, independent masks, context
readiness ordering, real official-SDK initialize/load, and offline restart
behavior. These checks do not prove a real server join or natural human reply.
After an authorized deployment, record the matching connection receipt and
actual server presence; report a later human exchange separately.
