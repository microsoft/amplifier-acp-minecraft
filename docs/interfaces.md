# Minecraft service and interface map

Use the [vision](VISION.md) for intended value and the references below for
Minecraft behavior and exact interfaces. This page navigates those definitions;
it does not introduce another contract or a release inventory.

## Agreements

The [Minecraft agreement](../contracts/minecraft.md) holds the domain promises.
The six shared agreements have their own homes:

| When the question is about… | Read |
| --- | --- |
| Service roles, record ownership or how parts connect | [Composition](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/composition.md) |
| Audience, participation, speech or useful result return | [Interaction](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/interaction.md) |
| Accepting, amending, delegating or stopping work | [Work authority](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/work-authority.md) |
| New input, planning, context or uncertain recovery | [Work continuity](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/work-continuity.md) |
| Setup, saved connections, updates or restoration | [Installations](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/installations.md) |
| ACP, SDKs, optional capabilities or engine choice | [Engine compatibility](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/engine-compatibility.md) |

## Technical references

These references define supported schemas, configuration and operation details.
Examples and setup skills illustrate their use. Exact tool schemas are published
by the installed MCP endpoint; optional discovery follows the relevant reference.

| Boundary or outcome | Technical reference | Implementation entry point |
| --- | --- | --- |
| Server access, accounts, private routes and installation prerequisites | [Installation requirements](server-setup.md), [Xbox LAN compatibility](xbox-lan.md) | [Example configuration](../config.example.json), [context registration](../ops/register_context.py) |
| ACP client, saved-session replay, permissions and negotiated fallback | [Python SDK boundary](python-sdk.md), [adapter lifecycle](adapter-reference.md#healthy-work-action-leases-and-acp-lifecycle) | [Client](../acp_client.py), [controller](../adapter.py) |
| Observation, world tools, action receipts and recovery | [Adapter reference](adapter-reference.md) | [Body and MCP schemas](../body.cjs) |
| Human interaction, task-optional activity, Stop and concurrent planning | [Human-led play](human-led-play.md), [task intake](human-task-intake.md), [bounds](completion-bound-tasks.md) | [Task state](../workshop-state.cjs), [planner context](../planner_prompt.py) |
| Authorized private input from another experience | [Installation inputs](installation-inputs.md), [input outcomes](input-outcomes.md) | [Body](../body.cjs) |
| Public context discovery and full authorized evidence | [Context and presence](adapter-reference.md#optional-context-decisions-and-watches) | [Workshop context](../workshop-state.cjs) |
| Observable peer coordination and return to the original audience | [Huddles](huddles.md) | [Controller](../adapter.py) |
| Saved Add, Connect and Disconnect operations | [Saved connections](saved-connections.md) | [Connection command](../installation_connection.py), [Add command](../installation_connection_add.py) |
| Source/dependency updates, pure helpers and continuity | [Installation updates](../INSTALLATION-UPDATES-DESIGN.md) | [Participant](../installation_participant.py), [source provider](../installation_source_provider.py) |
| Capturing the player's view and delivering the image | [Screenshots](screenshots.md) | [Screenshot service](../screenshots.cjs) |

For development and disposable-world checks, use the
[verification reference](adapter-reference.md#development-and-verification) and
the relevant interface fixtures. The [setup skill](../skills/minecraft-server-setup/SKILL.md)
helps choose an installation path; it does not define additional commitments.
