import assert from "node:assert/strict";
import test from "node:test";

import { PCM16_200MS_CHUNK_BYTES, Pcm16Chunker } from "../src/public/audio-chunks.js";

test("PCM16_200MS_CHUNK_BYTES is 4,800 16-bit samples", () => {
  assert.equal(PCM16_200MS_CHUNK_BYTES, 4_800 * 2);
});

test("Pcm16Chunker batches small buffers into fixed-size chunks", () => {
  const chunker = new Pcm16Chunker(6);

  assert.deepEqual(chunker.push(Uint8Array.from([1, 2, 3, 4]).buffer), []);
  assert.equal(chunker.pendingBytes, 4);

  const first = chunker.push(Uint8Array.from([5, 6, 7, 8]).buffer);
  assert.equal(first.length, 1);
  assert.deepEqual([...first[0]], [1, 2, 3, 4, 5, 6]);
  assert.equal(chunker.pendingBytes, 2);

  const second = chunker.push(Uint8Array.from([9, 10, 11, 12, 13, 14]).buffer);
  assert.equal(second.length, 1);
  assert.deepEqual([...second[0]], [7, 8, 9, 10, 11, 12]);
  assert.equal(chunker.pendingBytes, 2);
});

test("Pcm16Chunker flushes leftover bytes and resets state", () => {
  const chunker = new Pcm16Chunker(6);
  chunker.push(Uint8Array.from([1, 2, 3]).buffer);

  const flushed = chunker.flush();

  assert.deepEqual([...flushed], [1, 2, 3]);
  assert.equal(chunker.pendingBytes, 0);
  assert.equal(chunker.flush(), null);
});
