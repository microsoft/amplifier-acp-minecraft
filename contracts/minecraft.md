# Participating in the Minecraft world

For people operating ACP players and experiences using their game tools and
context. The promise: an agent participates through its actual player, and the
adapter makes the meaning of game input, effects and observations dependable.

**Example:** Ask a player to carry supplies to a build site. The player finds a
route, uses its inventory and reports the observed handoff. A voice client can
inspect that result without turning private direction into public game chat.

## Minecraft commitments

1. **Act through the player's body.** Agent tools use the connected player's
   position, inventory, reach and survival mechanics. They expose no arbitrary
   shell, operator RCON, teleportation or item creation. Operator fixture helpers
   are separate from the agent tool surface. Supported operations and checks are
   defined in the [adapter reference](../docs/adapter-reference.md).

2. **Keep game sources recognizable.** Server-attributed chat, whispers, configured
   agent peers, roster events and observed movement retain their distinct meanings.
   A roster entry or readiness callback is not a new human instruction or proof
   of respawn. Private installation input identifies its authenticated caller and
   caller-asserted actor; it never fabricates a Minecraft player or public message.
   [Human-led play](../docs/human-led-play.md) and
   [installation inputs](../docs/installation-inputs.md) define the local paths.

3. **Enforce game effects at the body.** The installation's effective activity
   policy, any bound assignment, Stop and unresolved effects govern the next
   operation. Task-optional survival activity is an explicit policy, not a hidden
   task or a way to reopen an expired commission. Planned sequences use the same
   game checks as individual operations. The [policy and sequence reference](../docs/human-led-play.md)
   and [task intake reference](../docs/human-task-intake.md) define the controls.
   General acceptance, delegation and limit meanings live in
   [work authority](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/work-authority.md).

4. **Report physical evidence at its actual scope.** Movement results distinguish
   the reached destination from the intended route or larger assignment. Dropped
   items are not a verified transfer to a recipient. Container results use server
   snapshots, and uncertain placement or movement remains inspectable before a
   retry. A screenshot is a captured view, not independent construction verification.
   Recent context projections retain coverage and a path to full authorized
   evidence. See [tools and context](../docs/adapter-reference.md),
   [screenshots](../docs/screenshots.md) and [input outcomes](../docs/input-outcomes.md)
   for exact observations and failure behavior.

5. **Keep saved worlds and access routes distinct.** Each saved connection has its
   own home, session binding, control route and connection definition. Server-owned
   player identity, inventory and position stay associated with the intended world.
   Authenticated human gateways and trusted offline agent routes are separate;
   similar Java and Xbox names do not establish an account link. Minecraft's
   [installation requirements](../docs/server-setup.md),
   [saved connection phases](../docs/saved-connections.md) and
   [update participant](../INSTALLATION-UPDATES-DESIGN.md) apply the shared
   [installation agreement](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/installations.md)
   to those resources.

## Shared promises and technical detail

[Composition](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/composition.md)
owns service and record ownership;
[interaction](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/interaction.md)
owns audience, speech and participation meaning;
[work continuity](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/work-continuity.md)
owns input and recovery meaning; and
[engine compatibility](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/engine-compatibility.md)
owns protocol and engine choice, including optional integrations and fallback.
These shared promises are not redefined here.

The [interface map](../docs/interfaces.md) locates schemas, configuration, setup
and executable checks, including capability discovery for the installed adapter.

**Check:** Walk a route and verify arrival; transfer supplies and independently
inspect the recipient; interrupt a sequence and inspect partial effects. Exercise
public chat, a whisper and private installation input without crossing audiences.
Reconnect two saved worlds without mixing bindings or changing work. Compare
compact context with full evidence, and test the ordinary ACP fallback. Mechanical
fixtures use disposable worlds; fresh human play checks conversation and usefulness.

**Left open:** Building style, route and resource choices, agent reasoning strategy,
and product UX. Test new mechanics and server translations against their actual
world behavior; a protocol connection alone does not establish support.
