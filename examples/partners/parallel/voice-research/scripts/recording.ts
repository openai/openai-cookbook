import { execFile } from "node:child_process";
import { promisify } from "node:util";

// Decode the saved artifact itself: a track event or caption is not evidence
// that the rendered microphone and assistant channels contain audio.
export async function checkRecording(path: string) {
  const { stdout } = await promisify(execFile)(
    "ffmpeg",
    ["-v", "error", "-i", path, "-ar", "16000", "-ac", "2", "-f", "f32le", "pipe:1"],
    { encoding: "buffer", maxBuffer: 40_000_000, timeout: 15_000 },
  );
  const channels = ["microphone", "speaker"].map((name, channel) => {
    let peak = 0,
      energy = 0,
      activeFrames = 0,
      frameEnergy = 0;
    const samples = Math.floor(stdout.length / 8);
    for (let sample = 0; sample < samples; sample++) {
      const value = stdout.readFloatLE(sample * 8 + channel * 4);
      peak = Math.max(peak, Math.abs(value));
      energy += value * value;
      frameEnergy += value * value;
      if (sample % 160 === 159) {
        if (Math.sqrt(frameEnergy / 160) > 0.001) activeFrames++;
        frameEnergy = 0;
      }
    }
    return { name, peak, rms: samples ? Math.sqrt(energy / samples) : 0, active_ms: activeFrames * 10 };
  });
  return {
    duration_ms: Math.floor(stdout.length / 8) / 16,
    channels,
    pass: channels.every(channel => channel.active_ms >= 100),
  };
}
