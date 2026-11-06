# Artwork and texture layout

## Generation brief

Adapt this to the inspected reference; bracketed fields are design choices:

> Create a flat Minecraft classic player skin texture from the attached identity.
> Preserve [palette], [face features] and [one or two accessories]. Design on a
> 64×64 logical pixel grid, with an 8×8 front face and four-pixel arms. Use crisp
> pixel-art blocks without antialiasing, soft gradients, perspective, text labels
> or gridlines. Make eyes clearly separate from skin and accessories at 8×8.
> Use Minecraft's classic UV layout. Opaque base faces; transparent unused areas.
> If enlarging for output, use exact integer-sized solid pixel squares. Output
> the texture, not a rendered standing character.

Supply the canonical UV map when useful. Inspect the result: it may ignore grid,
dimensions, alpha or panel coordinates. Do not resize an entire noncanonical
sheet to 64×64. Map individual faces or regenerate the offending region. Preserve
the original output and measured map so later edits need no guessing.

For an existing skin, provide the actual atlas plus the portrait when useful;
specify which regions may change. Compare unchanged regions after the edit.
Editing only a rendered screenshot cannot preserve hidden sides reliably.

## Classic base mapping

`classic-uv.json` gives six faces per part in this order:
**top, bottom, right, front, left, back**, from the wearer's perspective.
Coordinates start at the top left; x increases right and y downward.
Rectangles are half-open `[x,x+width) × [y,y+height)`.

| Part | Key | Front rectangle |
| --- | --- | --- |
| Head | head | 8, 8, 8, 8 |
| Torso | body | 20, 20, 8, 12 |
| Right arm | ra | 44, 20, 4, 12 |
| Right leg | rl | 4, 20, 4, 12 |
| Left arm | la | 36, 52, 4, 12 |
| Left leg | ll | 20, 52, 4, 12 |

Optional outer layers have separate regions and are not packed by this base-only
utility. Head overlay is offset +32 x; torso/right arm/right leg +16 y;
left leg -16 x; left arm +16 x. Preserve transparency around accessories.
Do not accidentally cover base eyes with an opaque outer face.

## Lessons from use

- **Averaging large illustrated faces:** a previous packer used box filtering on
  generated panels. This blends small eyes/frames into surrounding colors.
  Nearest sampling avoids blending but still needs inspection for lost details.
- **Prompted UV is not measured UV:** generated sheets used unequal panel sizes
  despite explicit coordinates. Measure each face; don't copy another character's
  crops or infer symmetry without checking.
- **Missing surfaces:** generate or deliberately design a missing bottom/back/
  limb face. Stretching an unrelated strip produces a valid but poor texture.
- **Near-opaque export noise:** a generated atlas had alpha 252–254 in all 1,632
  sampled base pixels despite opaque-looking artwork. Inspect the sampled alpha
  distribution; explicitly normalize only near-opaque base samples, with unchanged
  RGB and a recorded threshold/count. Keep strict rejection of real holes. Do not
  disable alpha for the entire source or erase intentional overlay transparency.
- **Accessories at 8×8:** keep eyes separate from spectacle frames; a dark rim
  with no eye separation reads as a mask. There is no universal eye stencil.
- **Sharpness versus lighting:** flat PNG and daytime mapped previews distinguish
  blended artwork from dark illumination. Do not alter shared-world time or
  lighting merely to obtain a test screenshot.

These lessons do not prove every new texture passes. Keep private before/after
face crops and mapped previews when assessing an improvement.
