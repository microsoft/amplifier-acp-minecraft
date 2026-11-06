#!/usr/bin/env node
'use strict';
// Format conversion/validation only: no artwork generation, upload or installation.
const fs = require('node:fs');
const { PNG } = require('pngjs');
const UV = require('../references/classic-uv.json');
const PARTS = Object.keys(UV.parts);

function readPng(file) {
  const stat = fs.statSync(file);
  if (stat.size > 16 * 1024 * 1024) throw Error('PNG exceeds 16 MiB');
  const bytes = fs.readFileSync(file);
  if (bytes.length < 24 || !bytes.subarray(0, 8).equals(Buffer.from('89504e470d0a1a0a', 'hex')) ||
      bytes.toString('ascii', 12, 16) !== 'IHDR') throw Error('Expected PNG with IHDR');
  const width = bytes.readUInt32BE(16), height = bytes.readUInt32BE(20);
  if (!width || !height || width > 4096 || height > 4096) throw Error('PNG dimensions outside 1..4096');
  return PNG.sync.read(bytes);
}

function validate(image) {
  if (image.width !== 64 || image.height !== 64) throw Error('Classic atlas must be exactly 64x64');
  let basePixels = 0;
  const occupied = new Set();
  for (const [part, faces] of Object.entries(UV.parts)) {
    for (const [x, y, w, h] of faces) {
      for (let row = y; row < y + h; row++) for (let col = x; col < x + w; col++) {
        const pos = row * 64 + col;
        if (occupied.has(pos)) throw Error('Canonical base faces overlap');
        occupied.add(pos);
        if (image.data[pos * 4 + 3] !== 255) throw Error(`Nonopaque base pixel in ${part} at ${col},${row}`);
        basePixels++;
      }
    }
  }
  let partialAlphaOutsideBase = 0;
  for (let pos = 0; pos < 4096; pos++) {
    const a = image.data[pos * 4 + 3];
    if (!occupied.has(pos) && a > 0 && a < 255) partialAlphaOutsideBase++;
  }
  return { valid: true, model: 'classic', width: 64, height: 64, basePixels,
    partialAlphaOutsideBase, visualQuality: 'not_assessed',
    warnings: partialAlphaOutsideBase ? ['Partial alpha outside base: inspect overlays and unused regions.'] : [] };
}

function pack(source, layout) {
  const minimumBaseAlpha = layout.minimumBaseAlpha ?? 255;
  if (!Number.isInteger(minimumBaseAlpha) || minimumBaseAlpha < 250 || minimumBaseAlpha > 255) throw Error('minimumBaseAlpha must be an integer from 250 to 255');
  let normalizedBasePixels = 0;
  if (layout.width !== source.width || layout.height !== source.height) throw Error('Layout dimensions do not match source');
  if (!layout.parts || Object.keys(layout.parts).length !== PARTS.length ||
      Object.keys(layout.parts).some(p => !PARTS.includes(p))) throw Error('Layout requires exactly six classic parts');
  const output = new PNG({ width: 64, height: 64 });
  output.data.fill(0);
  for (const part of PARTS) {
    const faces = layout.parts[part];
    if (!Array.isArray(faces) || faces.length !== 6) throw Error(`${part} requires six ordered faces`);
    faces.forEach((rect, face) => {
      if (!Array.isArray(rect) || rect.length !== 4 || !rect.every(Number.isSafeInteger)) throw Error('Rectangle must contain four integers');
      const [x, y, w, h] = rect;
      if (x < 0 || y < 0 || w < 1 || h < 1 || x + w > source.width || y + h > source.height) throw Error('Source rectangle out of bounds');
      const [dx, dy, dw, dh] = UV.parts[part][face];
      for (let row = 0; row < dh; row++) for (let col = 0; col < dw; col++) {
        // Sample texel centers; never blend adjacent palette colors.
        const sx = x + Math.floor((col + 0.5) * w / dw);
        const sy = y + Math.floor((row + 0.5) * h / dh);
        const from = (sy * source.width + sx) * 4;
        const to = ((dy + row) * 64 + dx + col) * 4;
        if (source.data[from + 3] < minimumBaseAlpha) throw Error(`Nonopaque base sample in ${part} at ${sx},${sy}; below minimumBaseAlpha`);
        source.data.copy(output.data, to, from, from + 4);
        if (output.data[to + 3] !== 255) { output.data[to + 3] = 255; normalizedBasePixels++; }
      }
    });
  }
  validate(output);
  output.packing = { minimumBaseAlpha, normalizedBasePixels };
  return output;
}

function main(args) {
  if (args[0] === 'validate' && args.length === 2) {
    console.log(JSON.stringify(validate(readPng(args[1])), null, 2));
  } else if (args[0] === 'pack' && args.length === 4) {
    const result = pack(readPng(args[1]), JSON.parse(fs.readFileSync(args[2], 'utf8')));
    fs.writeFileSync(args[3], PNG.sync.write(result), { flag: 'wx' });
    console.log(JSON.stringify({ ...validate(result), output: args[3], sampling: 'nearest-center', layers: 'base-only', ...result.packing }, null, 2));
  } else throw Error('Usage: skin-atlas.cjs validate SKIN.png | pack SOURCE.png LAYOUT.json NEW.png');
}
if (require.main === module) {
  try { main(process.argv.slice(2)); } catch (error) { console.error(error.message); process.exitCode = 1; }
}
module.exports = { readPng, validate, pack };
