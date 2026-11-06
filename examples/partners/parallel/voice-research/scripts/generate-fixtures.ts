import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFile, writeFile, rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

const { values } = parseArgs({ options: { voice: { type: "string" } } });
const directory = fileURLToPath(new URL("../evals/fixtures/", import.meta.url));
const manifest: { id: string; text: string; file: string; sha256: string; synthetic: boolean }[] =
  JSON.parse(await readFile(directory + "manifest.json", "utf8"));
for (const fixture of manifest) {
  const temporary = directory + fixture.id + ".aiff";
  const file = directory + fixture.file;
  try {
    execFileSync("say", [...(values.voice ? ["-v", values.voice] : []), "-r", "160", "-o", temporary, fixture.text]);
    execFileSync("ffmpeg", [
      "-y",
      "-loglevel",
      "error",
      "-i",
      temporary,
      "-ar",
      "24000",
      "-ac",
      "1",
      "-c:a",
      "pcm_s16le",
      file,
    ]);
    const bytes = await readFile(file);
    if (bytes.length < 1000)
      throw new Error(
        "Speech generation returned empty audio. Check macOS speech service access or supply recorded WAV fixtures.",
      );
    fixture.sha256 = createHash("sha256").update(bytes).digest("hex");
    fixture.synthetic = true;
  } finally {
    await rm(temporary, { force: true });
  }
}
await writeFile(directory + "manifest.json", JSON.stringify(manifest, null, 2) + "\n");
console.log(
  "Created synthetic speech fixtures in evals/fixtures. These check the workflow; use human recordings for representative voice evaluation.",
);
