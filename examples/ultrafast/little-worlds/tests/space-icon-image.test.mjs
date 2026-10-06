import test from 'node:test';
import assert from 'node:assert/strict';
import sharp from 'sharp';
import { createSpaceIconGenerator, normalizeSpaceIcon, SPACE_ICON_MAX_BYTES } from '../server/space-icon-image.mjs';
import { devDayIconInstructions } from '../server/devday-theme.mjs';

const picture = (format = 'png') => sharp({ create: { width: 360, height: 240, channels: 3, background: '#879e77' } }).toFormat(format).toBuffer();
const jsonImage = buffer => Response.json({ data: [{ b64_json: buffer.toString('base64') }] });
const adapter = fetchImpl => createSpaceIconGenerator({ apiKey: 'test-key', fetchImpl });

test('space icons normalize real PNG, JPEG, and WebP images to bounded 256px WebP', async () => {
  for (const format of ['png', 'jpeg', 'webp']) {
    const result = await normalizeSpaceIcon(await picture(format));
    assert.deepEqual(Object.keys(result).sort(), ['data', 'mimeType']);
    assert.equal(result.mimeType, 'image/webp');
    const buffer = Buffer.from(result.data, 'base64');
    const metadata = await sharp(buffer).metadata();
    assert.equal(metadata.format, 'webp');
    assert.equal(metadata.width, 256);
    assert.equal(metadata.height, 256);
    assert.equal(metadata.pages || 1, 1);
    assert.ok(buffer.length < 256 * 1024);
  }
});

test('uploads honor EXIF orientation before cropping and strip metadata', async () => {
  const pixels = Buffer.alloc(400 * 200 * 3);
  for (let y = 0; y < 200; y++) for (let x = 0; x < 400; x++) {
    const offset = (y * 400 + x) * 3;
    pixels[offset + (x < 200 ? 0 : 2)] = 255;
  }
  const input = await sharp(pixels, { raw: { width: 400, height: 200, channels: 3 } }).withMetadata({ orientation: 6 }).jpeg().toBuffer();
  const { data } = await normalizeSpaceIcon(input);
  const output = Buffer.from(data, 'base64');
  const metadata = await sharp(output).metadata();
  assert.equal(metadata.orientation, undefined);
  assert.equal(metadata.exif, undefined);
  assert.equal(metadata.icc, undefined);
  const raw = await sharp(output).raw().toBuffer();
  const top = (32 * 256 + 128) * 3;
  const bottom = (224 * 256 + 128) * 3;
  assert.ok(raw[top] > 220 && raw[top + 2] < 30, 'red left half becomes the top after EXIF rotation');
  assert.ok(raw[bottom + 2] > 220 && raw[bottom] < 30, 'blue right half becomes the bottom');
});

test('uploads reject unsupported formats, malformed image data, and excessive input', async () => {
  for (const invalid of [null, '', Buffer.alloc(0), Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>'), Buffer.from('GIF89a')]) {
    await assert.rejects(normalizeSpaceIcon(invalid), /PNG, JPEG, or WebP/);
  }
  await assert.rejects(normalizeSpaceIcon(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])), /could not be read/);
  await assert.rejects(normalizeSpaceIcon(Buffer.alloc(SPACE_ICON_MAX_BYTES + 1)), /under 5 MB/);
  const oversized = await sharp({ create: { width: 5001, height: 5000, channels: 3, background: 'white' } }).png().toBuffer();
  await assert.rejects(normalizeSpaceIcon(oversized), /25 megapixels/);
});

test('uploads reject animations even when a decoder could expose only the first frame', async () => {
  const png = await picture();
  const animationChunk = Buffer.alloc(20);
  animationChunk.writeUInt32BE(8, 0);
  animationChunk.write('acTL', 4);
  animationChunk.writeUInt32BE(2, 8);
  const apng = Buffer.concat([png.subarray(0, 33), animationChunk, png.subarray(33)]);
  await assert.rejects(normalizeSpaceIcon(apng), /still image/);
  const animated = await sharp(Buffer.from([255, 0, 0, 0, 0, 255]), { raw: { width: 1, height: 2, channels: 3, pageHeight: 1 } }).webp({ loop: 0, delay: [100, 100] }).toBuffer();
  assert.equal((await sharp(animated, { animated: true }).metadata()).pages, 2);
  await assert.rejects(normalizeSpaceIcon(animated), /still image/);
});

test('image generation applies shared DevDay art direction to a centered subject and returns only normalized image bytes', async () => {
  const input = await picture();
  let call;
  const generate = createSpaceIconGenerator({ apiKey: '  secret-test-key  ', model: 'test-image-model', fetchImpl: async (url, options) => { call = { url, options }; return jsonImage(input); } });
  const result = await generate({ description: 'A botanical journal with fern leaves and sage green.' });
  assert.equal(call.url, 'https://api.openai.com/v1/images/generations');
  assert.equal(call.options.method, 'POST');
  assert.equal(call.options.headers.Authorization, 'Bearer secret-test-key');
  assert.ok(call.options.signal instanceof AbortSignal);
  const body = JSON.parse(call.options.body);
  assert.equal(body.model, 'test-image-model');
  assert.equal(body.quality, 'low');
  assert.equal(body.size, '1024x1024');
  assert.equal(body.output_format, 'webp');
  assert.equal(body.output_compression, 85);
  assert.equal(body.n, 1);
  assert.match(body.prompt, /botanical journal/);
  assert.ok(body.prompt.includes(devDayIconInstructions));
  for (const color of ['#04b84c', '#924ff7', '#006aff', '#ff8549']) assert.ok(body.prompt.toLowerCase().includes(color));
  assert.match(body.prompt, /old colors, materials, or styling.*yield to the DevDay art direction/);
  assert.match(body.prompt, /central 70%/);
  assert.match(body.prompt, /No words, letters/);
  assert.doesNotMatch(call.options.body, /secret-test-key/);
  assert.deepEqual(result, await normalizeSpaceIcon(input));
});

test('generation validates missing input and bounds descriptions before making a request', async () => {
  let calls = 0;
  const fetchImpl = async (_url, options) => {
    calls++;
    const prompt = JSON.parse(options.body).prompt;
    assert.ok(prompt.length < 7000 + devDayIconInstructions.length);
    assert.doesNotMatch(prompt, /outside-description-limit/);
    return jsonImage(await picture());
  };
  const generate = createSpaceIconGenerator({ apiKey: 'test-key', fetchImpl });
  for (const description of [undefined, null, '', '  ', 5]) await assert.rejects(generate({ description }), /Describe the space/);
  await assert.rejects(createSpaceIconGenerator({ apiKey: '', fetchImpl })({ description: 'Garden' }), /API key/);
  assert.equal(calls, 0);
  await generate({ description: `${'green '.repeat(3000)}outside-description-limit` });
  assert.equal(calls, 1);
});

test('provider and network failures never echo private response bodies or credentials', async () => {
  const secret = 'sk-private-key and private prompt';
  for (const status of [400, 401, 403, 429, 500]) {
    await assert.rejects(adapter(async () => new Response(secret, { status }))({ description: 'Garden' }), error => {
      assert.doesNotMatch(error.message, /sk-private-key|private prompt/);
      assert.match(error.message, status === 429 ? /busy/ : new RegExp(String(status)));
      return true;
    });
  }
  await assert.rejects(adapter(async () => { throw new Error(secret); })({ description: 'Garden' }), /could not connect/);
  await assert.rejects(adapter(async () => new Response(new ReadableStream({ pull(controller) { controller.error(new Error(secret)); } })))({ description: 'Garden' }), error => {
    assert.match(error.message, /interrupted/);
    assert.doesNotMatch(error.message, /sk-private-key|private prompt/);
    return true;
  });
});

test('generated response bodies are bounded before JSON parsing, including streaming responses', async () => {
  let canceled = false;
  const declared = new Response(new ReadableStream({ cancel() { canceled = true; } }), { headers: { 'content-length': 9 * 1024 * 1024 } });
  await assert.rejects(adapter(async () => declared)({ description: 'Garden' }), /too large/);
  assert.equal(canceled, true);
  canceled = false;
  const streamed = new Response(new ReadableStream({ pull(controller) { controller.enqueue(new Uint8Array(9 * 1024 * 1024)); }, cancel() { canceled = true; } }));
  await assert.rejects(adapter(async () => streamed)({ description: 'Garden' }), /too large/);
  assert.equal(canceled, true);
});

test('generation rejects missing, malformed, and undecodable generated image data', async () => {
  const replies = [new Response(null), new Response('{'), Response.json({ data: [] }), Response.json({ data: [{ b64_json: 'not base64!!' }] }), Response.json({ data: [{ b64_json: 'dGVzdA==' }] })];
  for (const response of replies) {
    await assert.rejects(adapter(async () => response)({ description: 'Garden' }), /image|PNG, JPEG, or WebP/);
  }
});

test('caller cancellation is preserved before requests and while fetching', async () => {
  const reason = new DOMException('Stopped by caller', 'AbortError');
  const aborted = new AbortController();
  aborted.abort(reason);
  await assert.rejects(adapter(() => { assert.fail('must not fetch an aborted request'); })({ description: 'Garden', signal: aborted.signal }), error => error === reason);
  const controller = new AbortController();
  const generate = adapter(async (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(signal.reason), { once: true });
    queueMicrotask(() => controller.abort(reason));
  }));
  await assert.rejects(generate({ description: 'Garden', signal: controller.signal }), error => error === reason);
});

test('cancellation interrupts a stalled response body and preserves the caller reason', async () => {
  const controller = new AbortController();
  const reason = new DOMException('Stopped by caller', 'AbortError');
  let canceled = false;
  const generate = adapter(async () => new Response(new ReadableStream({ pull() { controller.abort(reason); }, cancel() { canceled = true; } }, { highWaterMark: 0 })));
  await assert.rejects(generate({ description: 'Garden', signal: controller.signal }), error => error === reason);
  assert.equal(canceled, true);
});

test('generation times out without waiting forever for the provider', async () => {
  const keepAlive = setTimeout(() => {}, 1000);
  try {
    const generate = createSpaceIconGenerator({ apiKey: 'test-key', timeoutMs: 5, fetchImpl: async (_url, { signal }) => new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(signal.reason), { once: true })) });
    await assert.rejects(generate({ description: 'Garden' }), error => error.name === 'TimeoutError');
  } finally { clearTimeout(keepAlive); }
});
