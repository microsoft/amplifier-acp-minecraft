# Minecraft service and interface map

Use the [vision](VISION.md) for intended value and the references below for
Minecraft behavior and exact interfaces. This page navigates those definitions;
it does not introduce another contract or a release inventory.

## Shared agreements

Constellation's [family agreement](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/family.v1-candidate.md)
owns service roles, information ownership, interface responsibilities and the
self-contained installation baseline. Its
[interaction agreement](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/experience.v1-candidate.md)
owns common source, audience, delivery and outcome meanings. The
[shared interface map](https://github.com/microsoft/amplifier-constellation/blob/main/contracts/README.md)
locates the applicable agreements for attention, task admission, collaboration,
SDKs, updates and saved connections. Read the relevant agreement rather than
copying its promises into a new guide.

## Local definitions

The following references define the adapter's supported behavior. Examples and
setup skills illustrate their use; removing an illustration must not remove an
obligation. Exact tool schemas are published by the installed MCP endpoint, and
optional features require the discovery described by their reference.

| Boundary or outcome | Authoritative Minecraft reference | Implementation entry point |
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

The server owns world state and game identities. The body exposes tools and
records observations and effects; the controller delivers source input to the
selected ACP engine. Optional Instance services do not replace the body as the
enforcer of game effects. The installation-input credential has its own scoped
interface; it is not a public game identity or general body-control token.
The references above define these distinctions and their failure behavior.

## Choosing and checking a change

Start with the boundary that changes. A movement repair belongs with world tools;
an engine session format belongs to its engine; a shared source-delivery promise
needs the affected service owners. Preserve the supported ordinary ACP path when
adding an optional integration. Use [development checks](adapter-reference.md#development-and-verification)
and the relevant interface's fixtures, then verify the combined journey before
claiming a useful live result. Documentation review alone establishes no live
compatibility or deployment.
