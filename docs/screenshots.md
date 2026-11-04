# Player screenshots

An agent can capture a view from its Minecraft eyes, save the PNG locally,
inspect it, and explicitly attach it to a conversation. Capturing does not
publish to Slack or start another planner turn.

This optional renderer uses the player's already-loaded world, not a second
Minecraft login or a remote camera. It starts Chromium on demand, takes one
960×540 frame, and shuts it down. It does not move the player. No rendering
process or model requests run while idle.

## Install for one player

In that player's adapter checkout/application folder (Node 22 or newer):

```sh
npm ci --ignore-scripts
npm run build:screenshots
npx playwright install chromium
python3 ops/enable_screenshots.py \
  --config /path/to/player/config.json \
  --directory /path/to/agent/workspace/screenshots/minecraft
```

Linux hosts may need Chromium system libraries (`npx playwright install-deps
chromium`, with administrator assistance). `--browser-path` selects an already
installed Chromium executable. Each player can have its own application and
storage. No shared service is required. Install without optional packages if
screenshots are not wanted; they are disabled unless explicitly enabled.

Restart the body only when its controller has no active turn or action. Preserve
`workshop.json`, endpoint/session files, task deadlines and budgets. Reconnect the
same controller. Do not reset the task or world to install this capability.

The main game MCP endpoint adds `screenshot`, `screenshots`, `screenshot_read`.
An already configured `/presence/mcp` connection adds `minecraft_screenshot`,
`minecraft_screenshots`, `minecraft_screenshot_read` using its separate credential.
It still cannot move a player or begin a task. A capture writes a local file, so
it is **not** advertised as read-only: a native runtime in ask mode needs approval
or the exact owner-configured `allowed_mcp_mutations` entry
`http://127.0.0.1:PORT/presence/mcp#minecraft_screenshot`. Do not authorize all
mutating tools just to enable screenshots.

## Use from an agent's other conversations

Ask: “Take a screenshot of your Minecraft view and show me here.”

1. Call `minecraft_screenshot` (or `screenshot` from the game connection).
2. Read the returned image and receipt. The file path is on the adapter's host.
3. Explicitly attach that file using the agent runtime's generic image attachment
   capability. Native Constellation Runtime provides `workspace_attach_image`
   in versions containing the workspace image attachment feature. An older
   runtime can capture/save, but needs this feature before automatic sharing.
4. The current ACP client delivers the attachment. The Slack adapter uploads ACP
   images into the current Slack conversation using its normal `files:write`
   permission. Other ACP clients can display the same image.

The screenshot directory should be inside the **same agent's** granted workspace
on the same host (or an explicitly granted mount) so its runtime can read it.
A remote adapter's path is not automatically a local runtime path. Such clients
can consume the standard MCP image bytes or explicitly transfer them with their
own file tools. Never put Slack credentials or Slack posting logic in this adapter.

`look_at: {x,y,z}` aims a capture at a visible location within 64 blocks without
turning/moving the player. `label` records an optional short caption. Saved-image
reads accept only a returned capture ID, not an arbitrary file path. Captures
have a ten-second cooldown, a 2 MiB file limit, and a 256-file/256 MiB store limit;
move older files to an archive when full. Old captures are never silently deleted.

## What the image means

The PNG is a rendered player view from loaded server geometry, not a recording
of an official Minecraft client. It covers at most five by five loaded chunks.
Unloaded areas are absent; screenshots cannot establish that an unseen area is
empty. Lighting is illustrative. Signs, skins and entities may look different
from the official client. It contains no HUD, private chat or desktop content.
Use block inspections/action receipts to verify construction or read signs.

A JSON receipt next to each PNG records player, world label, timestamps, camera
pose, dimensions, loaded chunk count and SHA-256. It records observations only;
it does not establish completion of an agent's task.

The renderer's temporary web endpoint binds loopback with an unpredictable path.
Browser requests are restricted to that endpoint; WebSockets and external
resources are blocked. There is no screenshot web server on the LAN.
