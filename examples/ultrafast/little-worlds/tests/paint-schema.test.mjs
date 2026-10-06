import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { validatePaintConfig, validatePaintPixels, paintValidationCode } from '../shared/paint-schema.mjs';

const canvas = (columns = 96, rows = 64) => ({ action: 'paint_pixels', columns, rows, color: 0, colorValue: '#123456', palette: ['#123456', '#fff'], background: '#ffffff' });

test('raster paint supports doubled and large resolutions with one compact character per pixel', () => {
  for (const [columns, rows] of [[1, 1], [96, 64], [192, 128], [256, 256]]) {
    const config = validatePaintConfig(canvas(columns, rows), true);
    const pixels = '.01'.repeat(Math.ceil(columns * rows / 3)).slice(0, columns * rows);
    assert.equal(validatePaintPixels(pixels, config), pixels);
    assert.ok(JSON.stringify(config).length + pixels.length < 70_000);
  }
});

test('legacy grids retain their existing size and palette contract', () => {
  const legacy = { action: 'paint_pixels', columns: 64, rows: 64, color: 31, colorValue: '#fff' };
  assert.deepEqual(validatePaintConfig(legacy), legacy);
  assert.throws(() => validatePaintConfig({ ...legacy, columns: 96 }), /1 to 64/);
});

test('raster paint rejects malformed dimensions, brush colors and palette data', () => {
  for (const [key, value] of [['columns', 257], ['rows', 0], ['columns', 1.1], ['rows', Infinity], ['color', 2], ['color', -1], ['palette', []], ['palette', Array(33).fill('#fff')], ['palette', ['red']], ['background', 'url(x)'], ['colorValue', '#fff'], ['action', '__proto__']]) {
    assert.throws(() => validatePaintConfig({ ...canvas(), [key]: value }, true), `${key}: ${value}`);
  }
  assert.throws(() => validatePaintConfig({ ...canvas(), unused: 'x'.repeat(4001) }, true), /4000/);
  assert.doesNotThrow(() => validatePaintConfig({ ...canvas(), color: 1, colorValue: '#FFFFFF' }, true));
  for (const value of [null, [], 'x', 3]) assert.throws(() => validatePaintConfig(value, true));
});

test('raster pixels require exact dimensions, declared colors and the documented alphabet', () => {
  const config = validatePaintConfig(canvas(2, 2), true);
  for (const pixels of ['', '...', '.....', '..02', '..0V', '..0<', '..0 ', null, ['.', '.', '0', '1']]) {
    assert.throws(() => validatePaintPixels(pixels, config));
  }
  const full = validatePaintConfig({ ...canvas(32, 1), palette: Array(32).fill('#123456') }, true);
  assert.equal(validatePaintPixels('0123456789abcdefghijklmnopqrstuv', full).length, 32);
  assert.throws(() => validatePaintPixels('.', { columns: 0, rows: 1, palette: ['#fff'] }));
});

test('serialized paint validators have no external dependencies', () => {
  const result = vm.runInNewContext(`${paintValidationCode}; const config = validatePaintConfig(input, true); validatePaintPixels(pixels, config);`, { input: canvas(2, 2), pixels: '..01' });
  assert.equal(result, '..01');
  const browser = vm.runInNewContext(`({ config: ${validatePaintConfig.toString()}, pixels: ${validatePaintPixels.toString()} })`);
  assert.equal(browser.pixels('....', browser.config(canvas(2, 2), true)), '....');
});
