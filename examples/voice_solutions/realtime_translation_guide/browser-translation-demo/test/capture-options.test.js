import assert from "node:assert/strict";
import test from "node:test";

import { buildDisplayMediaOptions } from "../src/public/capture-options.js";

test("buildDisplayMediaOptions requests local playback suppression when supported", () => {
  const options = buildDisplayMediaOptions({ suppressLocalAudioPlayback: true });

  assert.equal(options.audio.suppressLocalAudioPlayback, true);
  assert.equal(options.audio.echoCancellation, false);
  assert.equal(options.video.displaySurface, "browser");
});

test("buildDisplayMediaOptions omits local playback suppression when unsupported", () => {
  const options = buildDisplayMediaOptions({});

  assert.equal(Object.hasOwn(options.audio, "suppressLocalAudioPlayback"), false);
});
