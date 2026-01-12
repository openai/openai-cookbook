import { Codex } from '@openai/codex-sdk';
import fs from 'node:fs/promises';
import { diffWorktreeStream, resolveBaseCommitFromCommitHash, addWorktree, deleteWorktree } from './git.ts';

export type TaskRow = {
  name: string;
  commit_hash: string;
  summary: string;
  task: string;
  original_diff_path?: string;
  additional_context?: string;
};

export type SolveResult = {
  experimentDir: string;
  diffPath: string;
  codexLogPath: string;
  workTreeName: string;
  fullWorkingDirectory: string;
  commitHash: string;
  taskName: string;
  durationSeconds: number;
};

export async function solveTaskWithCodex(
  row: TaskRow,
  rowNumber: number,
  workingDirectory: string,
  outputDirectory: string,
  experiment: string,
  runId: string,
  codex: Codex,
): Promise<SolveResult> {
  const workTreeName = `wk-eval-${runId}-${row.commit_hash}`;
  const { baseCommit } = await resolveBaseCommitFromCommitHash(workingDirectory, row.commit_hash);
  await addWorktree(workTreeName, workingDirectory, baseCommit);
  const fullWorkingDirectory = `${workingDirectory}/${workTreeName}`;
  const thread = codex.startThread({
    skipGitRepoCheck: true,
    workingDirectory: fullWorkingDirectory,
    sandboxMode: 'workspace-write',
  });

  let experimentDir: string | undefined;
  try {
    const startNs = process.hrtime.bigint();
    const prompt = row.additional_context
      ? `${row.task}\n\nAdditional context:\n${row.additional_context}`
      : row.task;
    const result = await thread.run(prompt);
    const endNs = process.hrtime.bigint();
    const durationSeconds = Number(endNs - startNs) / 1e9;

    const diff = await diffWorktreeStream(fullWorkingDirectory, ['--no-color']);

    experimentDir = `${outputDirectory}/${experiment}`;
    await fs.mkdir(experimentDir, { recursive: true });
    await fs.mkdir(`${experimentDir}/diffs`, { recursive: true });
    await fs.mkdir(`${experimentDir}/codex_logs`, { recursive: true });

    const diffPath = `${experimentDir}/diffs/${row.name}.diff`;
    const codexLogPath = `${experimentDir}/codex_logs/${row.name}.codex.log`;
    await fs.writeFile(diffPath, diff);
    await fs.writeFile(codexLogPath, JSON.stringify(result, null, 2));

    return {
      experimentDir,
      diffPath,
      codexLogPath,
      workTreeName,
      fullWorkingDirectory,
      commitHash: row.commit_hash,
      taskName: row.name,
      durationSeconds,
    };
  } catch (error) {
    throw error;
  } finally {
    try {
      await deleteWorktree(workTreeName, workingDirectory);
    } catch { }
  }
}
