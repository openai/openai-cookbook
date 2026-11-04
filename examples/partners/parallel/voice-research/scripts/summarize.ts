import { readdir, readFile, writeFile } from "node:fs/promises";
import { resolve, join } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { summarize, type Annotation, type Rates, type Trial } from "./evaluation.ts";

const { values } = parseArgs({ options: { out: { type: "string" }, rates: { type: "string" } } });
if (!values.out) throw new Error("Use --out=evals/results/<run-directory> [--rates=evals/rates.json].");
const directory = resolve(values.out);
const rates = JSON.parse(
  await readFile(values.rates ?? fileURLToPath(new URL("../evals/rates.json", import.meta.url)), "utf8"),
) as Rates;
const trials = [];
for (const name of (await readdir(directory)).filter(name => name.endsWith("-trial.json")).sort()) {
  const trial = JSON.parse(await readFile(join(directory, name), "utf8")) as Trial;
  const annotation = JSON.parse(
    await readFile(join(directory, name.replace("-trial.json", "-annotation.json")), "utf8"),
  ) as Annotation;
  trials.push({ trial, annotation });
}
const report = summarize(trials, rates);
await writeFile(join(directory, "summary.json"), JSON.stringify({ rates, ...report }, null, 2) + "\n");
console.log(JSON.stringify(report, null, 2));
