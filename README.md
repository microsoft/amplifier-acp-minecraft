# Minecraft ACP adapter

Connect independent AI agents to Minecraft as ordinary players: they can talk,
explore, gather, build and collaborate using their own inventory and session.
Mineflayer supplies the body; this adapter exposes scoped Minecraft tools over
HTTP MCP to a standard ACP agent. Use Constellation, Codex, Claude or another
compatible ACP implementation—no custom world mod or shared agent memory required.

Part of [Amplifier Constellation](https://github.com/microsoft/amplifier-constellation).
Minecraft clients, servers, licensed accounts and game assets are obtained separately.

## Ask your agent to set it up

Point your agent at this repository and ask it to use the
[Minecraft server-setup skill](skills/minecraft-server-setup/SKILL.md).
For example:

> Use the server-setup skill in microsoft/amplifier-acp-minecraft to inspect my
> existing server, add an independent ACP player, and make the world reachable
> from my Xbox on the LAN. Preserve the world and current work. Tell me what
> needs my credentials or a real player test.

The skill covers fresh installations, existing-server upgrades, Java/Bedrock/Xbox
access, independent agent connections, behavior policies and idle updates. It
uses the [installation requirements](docs/server-setup.md) and loads only the relevant
specialist references. Agents that cannot discover repository skills can read
`skills/minecraft-server-setup/SKILL.md` directly.

## Direction and interfaces

Read the [vision](docs/VISION.md) for the intended player experience, the
[Minecraft agreement](contracts/minecraft.md) for domain promises, and the
[interface map](docs/interfaces.md) for the five-primitives mapping, shared
agreements and technical references.

Before installing, read the [installation requirements](docs/server-setup.md).
They cover engine/dependency compatibility, authenticated human access and private
agent routes, explicit behavior policies, and separate transport and human checks.

## Find the relevant reference

| What you want | Start here |
| --- | --- |
| Set up or upgrade a server and its players | [Setup skill](skills/minecraft-server-setup/SKILL.md) · [Installation requirements](docs/server-setup.md) |
| Native packages for Linux, macOS and Windows | [Private runtimes and qualification status](docs/native-packages.md) |
| Join from Xbox / Bedrock on LAN | [Gateway, discovery, authentication and verification](docs/xbox-lan.md) |
| Responsive conversation and continuous action plans | [Human-led play](docs/human-led-play.md) |
| Start/amend tasks naturally in chat | [Human task intake](docs/human-task-intake.md) |
| Completion-bound work and pure decision helpers | [Task bounds and helper discovery](docs/completion-bound-tasks.md) |
| Safe source, engine and helper updates | [Installation-owned updates](INSTALLATION-UPDATES-DESIGN.md) |
| Temporarily disconnect and reconnect saved players | [Saved connection controls](docs/saved-connections.md) |
| Create recognizable skins | [Agent-skin skill](skills/minecraft-agent-skins/SKILL.md) |
| Inspect queued input delivery without inferring fulfillment | [Private input outcomes](docs/input-outcomes.md) |
| Let agents take real screenshots | [Screenshot setup](docs/screenshots.md) |
| Configure tools, recovery, context and lifecycle | [Adapter reference](docs/adapter-reference.md) |
| Understand ACP compatibility and the official SDK | [Python SDK boundary](docs/python-sdk.md) |
| Run development and disposable-world checks | [Development and verification](docs/adapter-reference.md#development-and-verification) |

## Contributing

See [contributing guidance](docs/adapter-reference.md#contributing),
[code of conduct](CODE_OF_CONDUCT.md), [security policy](SECURITY.md) and
[support](SUPPORT.md). This project is licensed under [MIT](LICENSE).
Microsoft and third-party trademarks remain subject to their owners' guidelines;
see [trademarks](docs/adapter-reference.md#trademarks).
