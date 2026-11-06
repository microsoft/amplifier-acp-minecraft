'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { PNG } = require('pngjs');
const { validate, pack } = require('../skills/minecraft-agent-skins/scripts/skin-atlas.cjs');
const uv = require('../skills/minecraft-agent-skins/references/classic-uv.json');

function fixture() {
  const img = new PNG({ width: 64, height: 64 });
  for (let y = 0; y < 64; y++) for (let x = 0; x < 64; x++) {
    img.data.set([x * 4, y * 4, (x ^ y) * 4, 255], (y * 64 + x) * 4);
  }
  return img;
}
test('canonical asymmetric pixels retain orientation; base area and transparent regions match classic UV', () => {
  const src = fixture(), out = pack(src, uv);
  assert.equal(validate(out).basePixels, 1632);
  for (const [x, y] of [[8,8],[15,15],[20,20],[27,31],[44,20],[47,31],[36,52],[39,63],[20,52],[23,63]]) {
    const i = (y * 64 + x) * 4;
    assert.deepEqual(out.data.subarray(i, i + 4), src.data.subarray(i, i + 4));
  }
  assert.equal(out.data[(8 * 64 + 40) * 4 + 3], 0); // hat overlay not invented
});
test('integer-enlarged source preserves every base texel without blended colors', () => {
  const src = fixture(), big = new PNG({ width: 192, height: 192 });
  for (let y = 0; y < 192; y++) for (let x = 0; x < 192; x++) {
    const i = (Math.floor(y / 3) * 64 + Math.floor(x / 3)) * 4;
    src.data.copy(big.data, (y * 192 + x) * 4, i, i + 4);
  }
  const layout = { width: 192, height: 192, parts: Object.fromEntries(Object.entries(uv.parts).map(([p, f]) => [p, f.map(r => r.map(v => v * 3))])) };
  assert.deepEqual(pack(big, layout).data, pack(src, uv).data);
});
test('reject invalid mapping, source size mismatch, missing faces, and translucent base', () => {
  const src = fixture();
  for (const change of [l => l.width++, l => l.parts.head.pop(), l => l.parts.head[0][0] = -1,
    l => l.parts.head[0][2] = 100, l => l.parts.head[0][0] = 1.5, l => l.parts.extra = []]) {
    const layout = structuredClone(uv); change(layout);
    assert.throws(() => pack(src, layout));
  }
  src.data[(8 * 64 + 8) * 4 + 3] = 127;
  assert.throws(() => pack(src, uv), /Nonopaque/);
  assert.throws(() => validate(new PNG({ width: 128, height: 128 })), /64x64/);
});
test('overlay alpha is diagnostic; CLI round trip refuses overwriting existing artwork', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'skin-atlas-'));
  try {
    const src = pack(fixture(), uv);
    src.data[(8 * 64 + 40) * 4 + 3] = 128;
    assert.equal(validate(src).partialAlphaOutsideBase, 1);
    const image = path.join(dir, 'source.png'), map = path.join(dir, 'map.json'), out = path.join(dir, 'out.png');
    fs.writeFileSync(image, PNG.sync.write(src)); fs.writeFileSync(map, JSON.stringify(uv));
    const script = path.resolve(__dirname, '../skills/minecraft-agent-skins/scripts/skin-atlas.cjs');
    assert.equal(spawnSync(process.execPath, [script, 'pack', image, map, out]).status, 0);
    const before = fs.readFileSync(out);
    assert.notEqual(spawnSync(process.execPath, [script, 'pack', image, map, out]).status, 0);
    assert.deepEqual(fs.readFileSync(out), before);
    const check = spawnSync(process.execPath, [script, 'validate', out], { encoding: 'utf8' });
    assert.equal(check.status, 0); assert.equal(JSON.parse(check.stdout).visualQuality, 'not_assessed');
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});
test('near-opaque generated base can be normalized only by explicit bounded threshold, with unchanged RGB', () => {
  const src = fixture(), pos = (8 * 64 + 8) * 4;
  src.data[pos + 3] = 252;
  assert.throws(() => pack(src, uv), /Nonopaque/);
  const out = pack(src, { ...uv, minimumBaseAlpha: 252 });
  assert.equal(out.packing.normalizedBasePixels, 1);
  assert.equal(out.data[pos + 3], 255);
  assert.deepEqual(out.data.subarray(pos, pos + 3), src.data.subarray(pos, pos + 3));
  assert.equal(src.data[pos + 3], 252); // original artwork remains untouched
  src.data[pos + 3] = 249;
  assert.throws(() => pack(src, { ...uv, minimumBaseAlpha: 250 }), /Nonopaque/);
  for (const minimumBaseAlpha of [0, 249, 256, 252.5, '252']) assert.throws(() => pack(src, { ...uv, minimumBaseAlpha }), /minimumBaseAlpha/);
});
