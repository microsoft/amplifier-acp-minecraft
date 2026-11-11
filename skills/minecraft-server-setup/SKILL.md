---
name: minecraft-server-setup
description: Set up, connect, verify or upgrade a Minecraft server and independent ACP players, including Java/Bedrock/Xbox LAN gateways and installation-owned updates. Use for server/player operations and troubleshooting; use the separate skin skill for artwork.
---

# Minecraft server and player setup

Operate the user's requested server and installations, preserving existing worlds,
identities and work. This skill is portable across ACP engines and owners. It does
not assume the author's hosts, ports, accounts, model, systemd layout or policies.

## Inspect before selecting a path

Read [the installation requirements](../../docs/server-setup.md). Determine whether the request
is for a new world, an existing world, a player connection, a gateway repair,
behavior policy, or an update. Inventory the actual versions, service owners,
listeners, routes, saved sessions and in-flight work before changing an existing
installation. Resolve current coordination receipts by request ID and time;
delayed notes do not reopen completed holds or authorize duplicate restarts.

Use available configuration and connected evidence before asking the user for
missing details. Proceed within the authorization already provided. Ask only for
material choices, external account authorization or missing access; do not turn
routine reversible staging into another approval flow.

## Route to the needed reference

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

## Apply the installation boundary

Use the requirements in [staging and routes](../../docs/server-setup.md#3-stage-one-self-contained-player),
[behavior choices](../../docs/server-setup.md#4-choose-behavior-explicitly),
[layered verification](../../docs/server-setup.md#5-start-and-verify-in-layers) and
[recovery](../../docs/server-setup.md#6-updates-recovery-and-handoff). They define
what must survive and what the requested operation permits. This skill navigates
those requirements; it does not add a second authority or lifecycle policy.

For example, fixing Xbox discovery normally affects its human gateway, while a
player source update uses that player's lifecycle participant. Choose the
smallest relevant operation from the inspected topology, rather than restarting
everything. A fresh no-start installation and a used connection have different
session-verification paths; follow the applicable reference.

## Close with meaningful evidence

Use the evidence requirements in [verification](../../docs/server-setup.md#5-start-and-verify-in-layers)
and [handoff](../../docs/server-setup.md#6-updates-recovery-and-handoff) to close the
requested operation. Report what was actually checked and what still requires
the person's console or account. Keep private installation material out of the
publication checkout.

When a setup failure teaches a reusable lesson, update the smallest relevant
reference or tested helper. Keep examples illustrative and link to the governing
requirement instead of adding another definition here or in the README.
