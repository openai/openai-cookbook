import { describe, expect, it } from "vitest";
import {
  base64ToInt16,
  int16ToBase64,
  mulawBase64ToPcm16,
  pcm16ToMulawBase64,
  resampleLinear,
} from "../src/audio.js";

describe("audio conversion", () => {
  it("round trips PCM16 through base64", () => {
    const samples = new Int16Array([-32768, -1000, 0, 1000, 32767]);
    expect(base64ToInt16(int16ToBase64(samples))).toEqual(samples);
  });

  it("resamples 8 kHz telephony audio to 24 kHz model audio", () => {
    const samples = new Int16Array(160);
    const upsampled = resampleLinear(samples, 8000, 24000);
    expect(upsampled).toHaveLength(480);
  });

  it("resamples 24 kHz model audio to 8 kHz telephony audio", () => {
    const samples = new Int16Array(4800);
    const downsampled = resampleLinear(samples, 24000, 8000);
    expect(downsampled).toHaveLength(1600);
  });

  it("converts Twilio mulaw payloads into PCM16 and back", () => {
    const pcm = new Int16Array([0, 1000, -1000, 4000, -4000]);
    const payload = pcm16ToMulawBase64(pcm);
    const decoded = mulawBase64ToPcm16(payload);

    expect(decoded).toHaveLength(pcm.length);
    expect(Math.abs(decoded[0])).toBeLessThan(200);
  });
});
