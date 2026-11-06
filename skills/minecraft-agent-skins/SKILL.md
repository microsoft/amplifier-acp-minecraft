---
name: minecraft-agent-skins
description: Create, refine, validate, and install recognizable Minecraft agent skins from portraits or existing textures. Use for Minecraft player skin artwork and texture mapping, not general portraits or game behavior.
---

# Minecraft agent skins

Turn an agent's approved identity into a readable player skin. Use the host's
available image-generation/editing capability for artwork; this skill supplies
Minecraft-specific constraints and verification. It does not require a particular
model, provider, ACP engine, or central provisioning service.

## Choose the target and preserve identity

Inspect the portrait and any existing skin before editing. Keep the identifying
palette, face shape and one or two recognizable accessories. Ask only if the
identity or target is missing. A skin refresh changes appearance, not the agent's
identity, session, engine, or construction authorization.

For a Java-compatible shared-world skin, start with a **64×64 classic (four-pixel
arms) PNG**, unless the existing character or user calls for slim. The included
utilities intentionally support classic only. Do not silently label a slim texture
classic or assume a Bedrock Character Creator's extra geometry can become a flat
Java skin. A beard, spectacles or clipboard must be suggested within the available
head/body pixels and optional outer layer.

## Design for the pixels players see

The face is **8×8 pixels**, not a miniature high-resolution portrait. Keep eyes
distinct from skin, hair and frames. Prefer deliberate color blocks and dark/light
separation to gradients and tiny decorative marks. Check accessories at native
size; simplify them when they aren't recognizable.

Read [artwork-and-layout.md](references/artwork-and-layout.md) for a generation
brief, UV conventions and failure examples. A generated image is artwork, **not
proof of a valid atlas**. Even a prompt listing exact UV coordinates can produce
uneven panels or the wrong dimensions.

Large artwork can look attractive but produce muddy eyes when averaged down.
Nearest-neighbor sampling preserves existing color boundaries; it cannot recover
details absent from the target grid and can lose narrow features. Review the
resulting face instead of assuming a resampling algorithm solved readability.
Do not sharpen the entire atlas indiscriminately.

## Pack and validate locally

Keep personal references, generated artwork, prompts and installation receipts
in the owner's private asset directory. Publish reusable improvements, generic
fixtures and helpers in this repository.

From this repository's root after `npm ci --ignore-scripts`:

```sh
node skills/minecraft-agent-skins/scripts/skin-atlas.cjs validate /absolute/skin.png
```

For an approved, **base-layer-only** generated atlas with noncanonical panels,
make a private JSON map with `width`, `height`, and `parts`. Use the part names
and six-face order in [classic-uv.json](references/classic-uv.json); each source
rectangle is `[x,y,width,height]`. Measure the actual source, excluding gutters
and labels. Then:

```sh
node skills/minecraft-agent-skins/scripts/skin-atlas.cjs pack /absolute/source.png /absolute/layout.json /absolute/new-skin.png
```

The packer samples selected faces without blending, creates an exact classic
base atlas, rejects transparent sampled base pixels and refuses overwrite. It
does **not** infer panels, fix artwork, preserve an existing outer layer, mirror
limbs, or prove correct face orientation. For an existing skin with overlays,
edit that texture while preserving its layout instead of using this base packer.

If inspected opaque artwork has only near-opaque export noise (for example alpha
252–254 throughout sampled base faces), the private map can explicitly set
`minimumBaseAlpha` from 250 to 255. Default 255 remains strict. The packer rejects
samples below that threshold, changes only accepted base alpha to 255, preserves
RGB, and reports the normalized pixel count. This is not a repair for holes,
intentional transparency, incorrect crops or overlays. See the source alpha first.

Validate dimensions, opaque base faces and partial-alpha diagnostics. Inspect
the 8×8 face at native size and enlarged with nearest-neighbor, then view the
mapped character from front, back and both sides. Verify top/bottom, limb seams,
hands, boots and whether overlays hide the eyes. Numerical validation does not
establish resemblance or visual quality. Compare revisions under similar lighting.

## Install only when requested and verify

Read [installation.md](references/installation.md) for account versus server
installation, signing, refresh and evidence. Inspect the actual server mechanism;
do not assume a plugin, world path, version or UUID.

Creation alone need not install anything. When installation is authorized,
preserve current player/task/session state. Prefer a supported skin refresh.
Coordinate an idle boundary if a reconnect/restart is necessary; do not restart
the world or other agents for a cosmetic update.

Deliver the final PNG, a useful mapped preview, selected model, and what was
actually checked. Separate file validation, server texture delivery and client
appearance. Health checks alone prove neither delivery nor appearance. Record
pending visual verification honestly.

## Improve from evidence

When a real failure reveals a repeatable technique, update the relevant guide or
helper here with the fix and its limits. Add regressions for mapping/validation
defects; keep personal before/after evidence private. Do not hard-code one person's
face, host, player name or credentials. Do not call an untested technique proven.
Keep generic image-generation instructions in the host's image tooling; keep
Minecraft UV, pixel readability and skin delivery in this adapter skill.
