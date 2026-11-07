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

The current delta advertises existing connections only. It intentionally has
no Add link or form: creating a new connection still uses the setup guide.
Only advertise Add once a usable owner setup provider has been implemented
and enrolled; a link to documentation is not an interactive setup flow.

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
- Each action/revision/request is durably journaled before effects. After a lost
  reply, the host uses status only. Status may advance the same accepted
  operation; it never invents a replacement operation or repeats an uncertain
  service dispatch. Unknown settlement remains visible and requires owner
  investigation. A confirmed verification failure returns a settled failed
  result only after disconnecting safely.

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
