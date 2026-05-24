const MULAW_BIAS = 0x84;
const MULAW_CLIP = 32635;

export function base64ToInt16(base64) {
  const bytes = Buffer.from(base64, "base64");
  const samples = new Int16Array(Math.floor(bytes.length / 2));
  for (let index = 0; index < samples.length; index += 1) {
    samples[index] = bytes.readInt16LE(index * 2);
  }
  return samples;
}

export function int16ToBase64(samples) {
  const bytes = Buffer.alloc(samples.length * 2);
  for (let index = 0; index < samples.length; index += 1) {
    bytes.writeInt16LE(clampInt16(samples[index]), index * 2);
  }
  return bytes.toString("base64");
}

export function mulawBase64ToPcm16(base64) {
  const bytes = Buffer.from(base64, "base64");
  const samples = new Int16Array(bytes.length);
  for (let index = 0; index < bytes.length; index += 1) {
    samples[index] = mulawToPcm16(bytes[index]);
  }
  return samples;
}

export function pcm16ToMulawBase64(samples) {
  const bytes = Buffer.alloc(samples.length);
  for (let index = 0; index < samples.length; index += 1) {
    bytes[index] = pcm16ToMulaw(samples[index]);
  }
  return bytes.toString("base64");
}

export function resampleLinear(samples, fromRate, toRate) {
  if (fromRate === toRate) {
    return new Int16Array(samples);
  }

  const outputLength = Math.max(1, Math.round((samples.length * toRate) / fromRate));
  const output = new Int16Array(outputLength);
  const ratio = fromRate / toRate;

  for (let index = 0; index < output.length; index += 1) {
    const sourceIndex = index * ratio;
    const leftIndex = Math.floor(sourceIndex);
    const rightIndex = Math.min(samples.length - 1, leftIndex + 1);
    const fraction = sourceIndex - leftIndex;
    const left = samples[leftIndex] ?? 0;
    const right = samples[rightIndex] ?? left;
    output[index] = clampInt16(Math.round(left + (right - left) * fraction));
  }

  return output;
}

export function twilioMediaToRealtimeAudio(payload) {
  const pcm8k = mulawBase64ToPcm16(payload);
  return int16ToBase64(resampleLinear(pcm8k, 8000, 24000));
}

export function realtimeAudioToTwilioMedia(delta) {
  const pcm24k = base64ToInt16(delta);
  return pcm16ToMulawBase64(resampleLinear(pcm24k, 24000, 8000));
}

function pcm16ToMulaw(sample) {
  let pcm = clampInt16(sample);
  let sign = 0;

  if (pcm < 0) {
    pcm = -pcm;
    sign = 0x80;
  }

  pcm = Math.min(MULAW_CLIP, pcm) + MULAW_BIAS;

  let exponent = 7;
  for (let mask = 0x4000; (pcm & mask) === 0 && exponent > 0; mask >>= 1) {
    exponent -= 1;
  }

  const mantissa = (pcm >> (exponent + 3)) & 0x0f;
  return ~(sign | (exponent << 4) | mantissa) & 0xff;
}

function mulawToPcm16(byte) {
  const value = ~byte & 0xff;
  const sign = value & 0x80;
  const exponent = (value >> 4) & 0x07;
  const mantissa = value & 0x0f;
  let sample = ((mantissa << 3) + MULAW_BIAS) << exponent;
  sample -= MULAW_BIAS;
  return sign ? -sample : sample;
}

function clampInt16(value) {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(-32768, Math.min(32767, Math.trunc(value)));
}
