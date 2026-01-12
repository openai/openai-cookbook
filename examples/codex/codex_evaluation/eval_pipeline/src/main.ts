import fs from 'node:fs/promises';
import path from 'node:path';
import { Command } from 'commander';
import { Codex } from '@openai/codex-sdk';
import { parse as parseYaml } from 'yaml';
import { z } from 'zod';
import type { TaskRow, SolveResult } from './solver.ts';
import { solveTaskWithCodex } from './solver.ts';
import { getCommitDiff, gradeTask } from './grader.ts';
import {
  buildExperimentRunName,
  finalizeResults,
  generateRunId,
  getExperimentDir,
  initResults,
  recordTask,
  recomputeSummary,
  writeResults,
  extractUsageFromCodexLog,
} from './reporting.ts';

const YamlTaskSchema = z.object({
  name: z.string().min(1).regex(/^[A-Za-z0-9_-]+$/, 'name must be alphanumeric, underscores, or dashes (no spaces)'),
  commit_hash: z.coerce.string().min(1, 'commit_hash is required'),
  patch_summary: z.string().min(1),
  task_prompt: z.string().min(1),
  additional_context: z.string().optional(),
});

const YamlInputSchema = z.object({ tasks: z.array(YamlTaskSchema) });

async function readYamlTasks(filePath: string): Promise<TaskRow[]> {
  const absolutePath = path.resolve(filePath);

  let raw: string;
  try {
    raw = await fs.readFile(absolutePath, 'utf8');
  } catch (err) {
    throw new Error(`Cannot read file "${absolutePath}": ${(err as Error).message}`);
  }

  let parsed: unknown;
  try {
    parsed = parseYaml(raw);
  } catch (err) {
    throw new Error(`Invalid YAML: ${(err as Error).message}`);
  }

  let rows: TaskRow[];
  try {
    const validated = YamlInputSchema.parse(parsed);
    rows = validated.tasks.map((t): TaskRow => {
      const base: TaskRow = {
        name: t.name,
        commit_hash: String(t.commit_hash),
        summary: t.patch_summary,
        task: t.task_prompt,
      };
      if (typeof t.additional_context === 'string' && t.additional_context.length > 0) {
        (base as unknown as Record<string, unknown>).additional_context = t.additional_context;
      }
      return base;
    });
  } catch (err) {
    const issues = (err as z.ZodError).issues
      ?.map((i) => `- ${i.path.join('.') || '(root)'}: ${i.message}`)
      .join('\n') ?? String(err);
    throw new Error(`Schema validation failed:\n${issues}`);
  }

  return rows;
}

async function processTasks(
  filePath: string,
  workingDirectory: string,
  outputDirectory: string,
  experimentName: string,
  model: string,
  reasoningEffort: string,
  runId: string,
  repeat: number,
): Promise<void> {
  const rows = await readYamlTasks(filePath);
  const codex = new Codex();

  const styles = {
    bold: (s: string) => `\x1b[1m${s}\x1b[0m`,
    cyan: (s: string) => `\x1b[36m${s}\x1b[0m`,
    gray: (s: string) => `\x1b[90m${s}\x1b[0m`,
    green: (s: string) => `\x1b[32m${s}\x1b[0m`,
    red: (s: string) => `\x1b[31m${s}\x1b[0m`,
    dim: (s: string) => `\x1b[2m${s}\x1b[0m`,
  };

  const startedAt = new Date().toISOString();
  const experimentRunName = buildExperimentRunName(experimentName, runId);
  const { results, resultsPath } = await initResults({
    experimentName,
    runId,
    startedAt,
    parameters: {
      tasksFile: filePath,
      workingDirectory,
      outputDir: outputDirectory,
      experiment: experimentName,
      model,
      reasoningEffort,
      repeat,
    },
    numTasks: rows.length,
    outputDir: outputDirectory,
  });

  for (let i = 0; i < rows.length; i += 1) {
    const row = rows[i];
    const header = `${styles.bold(`Task ${i + 1}/${rows.length}`)} ${row.name} ${styles.gray(`(commit=${row.commit_hash})`)}`;
    const hr = styles.gray('─'.repeat(Math.min(process.stdout.columns || 80, 80)));
    console.log(hr);
    console.log(header);
    console.log(hr);
    try {
      const runDir = getExperimentDir(outputDirectory, experimentRunName);
      const originalDir = `${runDir}/original_diffs`;
      await fs.mkdir(originalDir, { recursive: true });
      const originalPath = `${originalDir}/${row.name}.diff`;
      const changeDiff = await getCommitDiff(row.commit_hash, workingDirectory);
      await fs.writeFile(originalPath, changeDiff);
      row.original_diff_path = originalPath;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error(styles.red(`Failed to prepare original diff: ${msg}`));
    }

    let result: SolveResult | undefined;
    console.log(styles.dim('Running solver...'));
    try {
      result = await solveTaskWithCodex(row, i + 1, workingDirectory, outputDirectory, experimentRunName, runId, codex);
      console.log(styles.green('Completed'));
    } catch (err) {
      console.log(styles.red('Failed'));
      const message = err instanceof Error ? err.message : String(err);
      console.error(styles.red(`Error: ${message}`));
      try {
        recordTask(results, row, {
          success: false,
          errorMessage: message,
          error: message,
          originalDiffPath: row.original_diff_path,
        });
        recomputeSummary(results);
        await writeResults(resultsPath, results);
      } catch { }
      console.log(hr);
      continue;
    }

    if (result) {
      console.log(styles.bold('Outputs'));
      console.log(`  ${styles.gray('experimentDir')}: ${result.experimentDir}`);
      console.log(`  ${styles.gray('diffPath')}: ${result.diffPath}`);
      console.log(`  ${styles.gray('codexLogPath')}: ${result.codexLogPath}`);
      console.log(`  ${styles.gray('durationSeconds')}: ${result.durationSeconds.toFixed(3)}`);

      let diffContent = '';
      try {
        diffContent = await fs.readFile(result.diffPath, 'utf8');
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        const failureMessage = `Failed to read generated diff: ${msg}`;
        console.error(styles.red(failureMessage));
        try {
          const usage = await extractUsageFromCodexLog(result.codexLogPath);
          recordTask(results, row, {
            solve: result,
            success: false,
            errorMessage: failureMessage,
            error: failureMessage,
            originalDiffPath: row.original_diff_path,
            usage,
          });
          recomputeSummary(results);
          await writeResults(resultsPath, results);
        } catch { }
        console.log(hr);
        continue;
      }

      if (diffContent.trim().length === 0) {
        const failureMessage = 'Failed to generate a diff or change';
        console.error(styles.red(failureMessage));
        try {
          const usage = await extractUsageFromCodexLog(result.codexLogPath);
          recordTask(results, row, {
            solve: result,
            success: false,
            errorMessage: failureMessage,
            error: failureMessage,
            originalDiffPath: row.original_diff_path,
            usage,
          });
          recomputeSummary(results);
          await writeResults(resultsPath, results);
        } catch { }
        console.log(hr);
        continue;
      }

      console.log(styles.bold('Ground truth diff (original)'));
      try {
        const originalPath = row.original_diff_path;
        if (!originalPath) throw new Error('original_diff_path missing');
        const usage = await extractUsageFromCodexLog(result.codexLogPath);
        const grade = await gradeTask(
          originalPath,
          `${result.experimentDir}/diffs/${row.name}.diff`,
        );

        console.log('Grade:');
        console.log(JSON.stringify(grade, null, 2));
        try {
          recordTask(results, row, { solve: result, grade, success: true, originalDiffPath: originalPath, usage });
          recomputeSummary(results);
          await writeResults(resultsPath, results);
        } catch { }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        console.error(styles.red(`Grading failed: ${msg}`));
        try {
          const usage = await extractUsageFromCodexLog(result.codexLogPath);
          recordTask(results, row, { solve: result, grade: null, success: true, originalDiffPath: row.original_diff_path, usage });
          recomputeSummary(results);
          await writeResults(resultsPath, results);
        } catch { }
      }
    }
    console.log(hr);
  }
  finalizeResults(results, startedAt);
  await writeResults(resultsPath, results);
}

async function main(): Promise<void> {
  const program = new Command();
  program
    .name('codex-cli')
    .description('Evaluate Codex SDK prompt outputs for baseline evaluation patches')
    .version('1.0.0');

  program
    .command('solve')
    .description('Solve and evaluate tasks from a YAML file')
    .option('-t, --tasks <file>', 'Path to tasks YAML', 'data/tasks.yaml')
    .option('-w, --working-directory <dir>', 'Root path of the git repository', 'root_repo')
    .option('-o, --output-dir <dir>', 'Directory to write .diff outputs', 'evals_output')
    .option('-e, --experiment <name>', 'Experiment name for this run', 'default')
    .option('-m, --model <model>', 'Model to use for the experiment', 'gpt-5-codex')
    .option('-r, --reasoning-effort <effort>', 'Reasoning effort for the experiment', 'medium')
    .option('-n, --repeat <count>', 'Repeat experiment N times', '1')
    .action(async (opts: { tasks: string; workingDirectory: string; outputDir: string; experiment: string; model: string; reasoningEffort: string; repeat: string }) => {
      try {
        const exp = String(opts.experiment);
        const isValid = /^[A-Za-z0-9_-]+$/.test(exp);
        if (!isValid) {
          throw new Error('experiment must be alphanumeric, underscores, or dashes (no spaces)');
        }

        const repeat = Number.parseInt(String(opts.repeat), 10);
        if (!Number.isFinite(repeat) || repeat < 1) {
          throw new Error('repeat must be a positive integer');
        }

        for (let i = 0; i < repeat; i += 1) {
          const runId = generateRunId();
          await processTasks(
            opts.tasks,
            opts.workingDirectory,
            opts.outputDir,
            exp,
            opts.model,
            opts.reasoningEffort,
            runId,
            repeat,
          );
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        console.error(`Failed to process tasks: ${message}`);
        process.exitCode = 1;
      }
    });

  await program.parseAsync(process.argv);
}

void main();
