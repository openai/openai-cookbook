import assert from "node:assert/strict";
import test from "node:test";

async function importAudioMix() {
  try {
    return await import("../src/public/audio-mix.js");
  } catch (error) {
    assert.fail(
      `audio-mix.js should export browser audio mix helpers: ${error.message}`,
    );
  }
}

test("audio mix defaults to mostly translated audio with some original audio", async () => {
  const { DEFAULT_TRANSLATED_MIX, buildAudioMixState } = await importAudioMix();

  assert.equal(DEFAULT_TRANSLATED_MIX, 85);
  assert.deepEqual(buildAudioMixState(DEFAULT_TRANSLATED_MIX), {
    translatedPercent: 85,
    originalPercent: 15,
    translatedVolume: 0.85,
    originalVolume: 0.15,
    valueLabel: "85% translated",
    translatedLabel: "Translated 85%",
    originalLabel: "Original 15%",
  });
});

test("audio mix clamps slider values into valid volume percentages", async () => {
  const { buildAudioMixState } = await importAudioMix();

  assert.equal(buildAudioMixState("-1").translatedPercent, 0);
  assert.equal(buildAudioMixState("101").translatedPercent, 100);
  assert.equal(buildAudioMixState("not a number").translatedPercent, 85);
});
