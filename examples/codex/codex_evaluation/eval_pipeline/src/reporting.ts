import fs from 'node:fs/promises';
import { randomBytes } from 'node:crypto';
import type { TaskRow, SolveResult } from './solver.ts';

export type RunParameters = {
  tasksFile: string;
  workingDirectory: string;
  outputDir: string;
  experiment: string;
  model: string;
  reasoningEffort: string;
  repeat: number;
};

export type TaskGrade = {
  score: number;
  explanation: string;
} | null;

export type TaskOutputs = {
  diffPath?: string;
  codexLogPath?: string;
};

export type TaskGroundTruth = {
  originalDiffPath?: string;
};

export type TaskUsage = Record<string, unknown> | null;

export type TaskMetrics = {
  name: string;
  commit_hash: string;
  summary: string;
  durationSeconds?: number;
  outputs: TaskOutputs;
  groundTruth: TaskGroundTruth;
  grade: TaskGrade;
  success: boolean;
  errorMessage?: string | null;
  error?: string | null;
  usage?: TaskUsage;
};

export type RunSummary = {
  numTasks: number;
  numSucceeded: number;
  numFailed: number;
  averageDurationSeconds: number;
};

export type RunResults = {
  experimentName: string;
  runId: string;
  timestamp: string;
  startedAt: string;
  finishedAt?: string;
  durationSeconds?: number;
  parameters: RunParameters;
  summary: RunSummary;
  tasks: TaskMetrics[];
};

export function generateRunId(): string {
  return randomBytes(4).toString('hex').slice(0, 7);
}

export function buildExperimentRunName(experiment: string, runId: string): string {
  return `${experiment}-${runId}`;
}

export function getExperimentDir(outputDir: string, experimentRunName: string): string {
  return `${outputDir}/${experimentRunName}`;
}

export async function writeResults(filePath: string, results: RunResults): Promise<void> {
  await fs.writeFile(filePath, JSON.stringify(results, null, 2));
}

export async function initResults(params: {
  experimentName: string;
  runId: string;
  startedAt: string;
  parameters: RunParameters;
  numTasks: number;
  outputDir: string;
}): Promise<{ results: RunResults; resultsPath: string; experimentDir: string }> {
  const { experimentName, runId, startedAt, parameters, numTasks, outputDir } = params;
  const experimentRunName = buildExperimentRunName(experimentName, runId);
  const experimentDir = getExperimentDir(outputDir, experimentRunName);

  await fs.mkdir(experimentDir, { recursive: true });

  const results: RunResults = {
    experimentName,
    runId,
    timestamp: new Date(startedAt).toISOString(),
    startedAt: new Date(startedAt).toISOString(),
    parameters,
    summary: {
      numTasks,
      numSucceeded: 0,
      numFailed: 0,
      averageDurationSeconds: 0,
    },
    tasks: [],
  };

  const resultsPath = `${experimentDir}/results.json`;
  await writeResults(resultsPath, results);
  return { results, resultsPath, experimentDir };
}

export function recordTask(
  results: RunResults,
  task: TaskRow,
  data: {
    solve?: SolveResult;
    grade?: TaskGrade;
    success: boolean;
    errorMessage?: string | null;
    error?: string | null;
    originalDiffPath?: string;
    usage?: TaskUsage;
  },
): void {
  const metrics: TaskMetrics = {
    name: task.name,
    commit_hash: task.commit_hash,
    summary: task.summary,
    durationSeconds: data.solve?.durationSeconds,
    outputs: {
      diffPath: data.solve?.diffPath,
      codexLogPath: data.solve?.codexLogPath,
    },
    groundTruth: {
      originalDiffPath: data.originalDiffPath ?? task.original_diff_path,
    },
    grade: data.grade ?? null,
    success: data.success,
    errorMessage: data.errorMessage ?? null,
    error: data.error ?? data.errorMessage ?? null,
    usage: data.usage ?? null,
  };

  results.tasks.push(metrics);
}

export function recomputeSummary(results: RunResults): void {
  const numTasks = results.tasks.length > 0 ? results.tasks.length : results.summary.numTasks;
  const numSucceeded = results.tasks.filter((t) => t.success).length;
  const numFailed = results.tasks.filter((t) => !t.success).length;
  const durations = results.tasks
    .map((t) => t.durationSeconds)
    .filter((d): d is number => typeof d === 'number' && !Number.isNaN(d));
  const averageDurationSeconds = durations.length > 0
    ? durations.reduce((a, b) => a + b, 0) / durations.length
    : 0;

  results.summary = {
    numTasks,
    numSucceeded,
    numFailed,
    averageDurationSeconds,
  };
}

export function finalizeResults(results: RunResults, startedAt: string | Date): void {
  const start = new Date(startedAt).getTime();
  const finishedAt = new Date();
  const durationSeconds = (finishedAt.getTime() - start) / 1000;
  results.finishedAt = finishedAt.toISOString();
  results.durationSeconds = durationSeconds;
  recomputeSummary(results);
}

function findUsageInObject(obj: unknown): unknown | null {
  if (!obj || typeof obj !== 'object') return null;
  if (Object.prototype.hasOwnProperty.call(obj, 'usage')) {
    const anyObj = obj as Record<string, unknown>;
    const val = anyObj['usage'];
    if (val && typeof val === 'object') return val;
  }
  if (Array.isArray(obj)) {
    for (const item of obj) {
      const found = findUsageInObject(item);
      if (found) return found;
    }
    return null;
  }
  for (const v of Object.values(obj as Record<string, unknown>)) {
    const found = findUsageInObject(v);
    if (found) return found;
  }
  return null;
}

export async function extractUsageFromCodexLog(codexLogPath: string): Promise<TaskUsage> {
  try {
    const raw = await fs.readFile(codexLogPath, 'utf8');
    const parsed = JSON.parse(raw);
    const usage = findUsageInObject(parsed);
    return (usage && typeof usage === 'object') ? usage as Record<string, unknown> : null;
  } catch {
    return null;
  }
}
