---
name: minecraft-server-setup
description: Set up, connect, verify or upgrade a Minecraft server and independent ACP players, including Java/Bedrock/Xbox LAN gateways and installation-owned updates. Use for server/player operations and troubleshooting; use the separate skin skill for artwork.
---

# Minecraft server and player setup

Operate the user's requested server and installations, preserving existing worlds,
identities and work. This skill is portable across ACP engines and owners. It does
not assume the author's hosts, ports, accounts, model, systemd layout or policies.

## Inspect before selecting a path

Read [the setup guide](../../docs/server-setup.md). Determine whether the request
is for a new world, an existing world, a player connection, a gateway repair,
behavior policy, or an update. Inventory the actual versions, service owners,
listeners, routes, saved sessions and in-flight work before changing an existing
installation. Resolve current coordination receipts by request ID and time;
delayed notes do not reopen completed holds or authorize duplicate restarts.

Use available configuration and connected evidence before asking the user for
missing details. Proceed within the authorization already provided. Ask only for
material choices, external account authorization or missing access; do not turn
routine reversible staging into another approval flow.

## Route to the needed guide

- Fresh server, adding a player, or an existing-host upgrade:
  [server setup](../../docs/server-setup.md).
- Xbox / Bedrock / LAN visibility or authentication:
  [Xbox LAN](../../docs/xbox-lan.md). Discovery, transport and real login are
  separate. Preserve the authenticated human route; never expose the agent route.
- Natural human requests, limits, responsiveness or activity:
  [human-led play](../../docs/human-led-play.md),
  [task intake](../../docs/human-task-intake.md) and, if needed,
  [completion-bound helpers](../../docs/completion-bound-tasks.md).
- Updating source/dependencies, engine or shared components:
  [installation updates](../../INSTALLATION-UPDATES-DESIGN.md).
- Protocol, tools, context or recovery specifics: read only the relevant section
  of [the adapter reference](../../docs/adapter-reference.md) and
  [the SDK boundary](../../docs/python-sdk.md).
- Appearance: [agent-skin skill](../minecraft-agent-skins/SKILL.md).
  Screenshots: [setup guide](../../docs/screenshots.md).

## Operational invariants

Each player owns its installation, control/MCP route, credentials, identity,
session and authority. Preserve engine family and ordinary ACP fallback. Discover
optional attention, steering, receipt, maintenance and helper capabilities from
the installed implementation; a product name/version or another player's support
is not evidence. Use the pinned official Python SDK for framing and correlation.

Keep world/server/proxy, body/controller and Instance/runtime lifecycles separate.
Restart only components needed for the requested change. An Xbox human-gateway
repair normally needs no agent or world restart. Source changes need a settled
body/controller cutover and continuity receipt. Use an enrolled update participant
when available; preserve its original active/stopped/masked state.

Never use setup or verification to renew expired work, convert prior limits,
replay unknown input, replace a used session, seed supplies or build a test design
in the family world. Disposable mechanical tests belong in a separate test world.
Fresh installs may remain chat-only with no task and no saved session; do not send
a synthetic model prompt just to create persistence. Existing installations verify
their original saved session, not a replacement.

## Close with meaningful evidence

Record selected source/artifact/dependency hashes, policy changes, service/route
checks, original-session and authority continuity, and rollback information in
private owner storage. Keep secrets, addresses, personal art and transcripts out
of publication checkouts.

Separate code/test success, installed capability, transport readiness and actual
human behavior. A successful handshake does not prove a console authenticated;
a receipt accepted does not prove incorporated/completed; an active controller
is not a successful new turn. Finish all independent checks before asking for a
real console join or fresh human request that only the user can supply.

When a setup failure teaches a reusable lesson, update the smallest relevant
reference or tested helper. Keep machine-specific workarounds and evidence private;
do not add speculative universal rules or duplicate the guide in the README.
