// Self-contained validators shared by the publishing runtime and opaque frame.
export function validatePaintConfig(value, raster = false) {
  const fail = message => { throw new Error(message); };
  const hex = color => typeof color === 'string' && /^#(?:[\da-f]{3}|[\da-f]{6})$/i.test(color);
  const expanded = color => (color.length === 4 ? '#' + [...color.slice(1)].map(char => char + char).join('') : color).toLowerCase();
  if (!value || typeof value !== 'object' || Array.isArray(value)) fail('Paint configuration must be an object.');
  if (JSON.stringify(value).length > 4000) fail('Paint configuration exceeds 4000 characters.');
  if (typeof value.action !== 'string' || !/^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(value.action)
    || ['constructor', 'prototype', '__proto__'].includes(value.action)) fail('Paint configuration requires a valid action name.');
  const maximum = raster ? 256 : 64;
  if (!Number.isInteger(value.columns) || value.columns < 1 || value.columns > maximum
    || !Number.isInteger(value.rows) || value.rows < 1 || value.rows > maximum) {
    fail(`Paint ${raster ? 'canvas' : 'grid'} dimensions must be whole numbers from 1 to ${maximum}.`);
  }
  if (!Number.isInteger(value.color) || value.color < 0 || value.color > 31 || !hex(value.colorValue)) {
    fail('Paint configuration requires a palette index from 0 to 31 and a hexadecimal preview color.');
  }
  const result = { action: value.action, columns: value.columns, rows: value.rows, color: value.color, colorValue: value.colorValue };
  if (raster) {
    if (!Array.isArray(value.palette) || value.palette.length < 1 || value.palette.length > 32 || !value.palette.every(hex)
      || value.color >= value.palette.length || !hex(value.background)) fail('Paint canvas requires 1 to 32 hexadecimal palette colors and a hexadecimal background.');
    if (expanded(value.colorValue) !== expanded(value.palette[value.color])) fail('Paint preview color must match the selected palette color.');
    result.palette = [...value.palette];
    result.background = value.background;
  }
  return result;
}

export function validatePaintPixels(pixels, config) {
  if (!config || !Number.isInteger(config.columns) || config.columns < 1 || config.columns > 256
    || !Number.isInteger(config.rows) || config.rows < 1 || config.rows > 256
    || !Array.isArray(config.palette) || config.palette.length < 1 || config.palette.length > 32) {
    throw new Error('Paint pixels require a valid canvas configuration.');
  }
  if (typeof pixels !== 'string' || pixels.length !== config.columns * config.rows) {
    throw new Error('Paint pixels must contain exactly one character per canvas cell.');
  }
  const alphabet = '0123456789abcdefghijklmnopqrstuv'.slice(0, config.palette.length);
  for (const pixel of pixels) if (pixel !== '.' && !alphabet.includes(pixel)) {
    throw new Error('Paint pixels must use a declared palette index (0–9, a–v) or . for background.');
  }
  return pixels;
}

export const paintValidationCode = `const paintValidators = (() => {
${validatePaintConfig.toString()}
${validatePaintPixels.toString()}
return { validatePaintConfig: ${validatePaintConfig.name}, validatePaintPixels: ${validatePaintPixels.name} };
})();
const { validatePaintConfig, validatePaintPixels } = paintValidators;`;
