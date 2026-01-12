import OpenAI from 'openai';
import { env } from 'node:process';
import fs from 'node:fs/promises';
import { z } from 'zod';
import { resolveBaseCommitFromCommitHash, runGitCapture } from './git.ts';
import { zodTextFormat } from 'openai/helpers/zod';

export const GradeResult = z.object({
  score: z.number().min(0).max(5),
  explanation: z.string().min(1),
});
export type Grade = z.infer<typeof GradeResult>;

/**
 * Returns the diff for the merged commit against its first parent (base commit).
 */
export async function getCommitDiff(commitHash: string, repoDir: string): Promise<string> {
  const { mergedCommit, baseCommit } = await resolveBaseCommitFromCommitHash(repoDir, commitHash);
  const diff = await runGitCapture(['diff', '--no-color', `${baseCommit}..${mergedCommit}`], repoDir);
  return diff;
}

/**
 * Grades the task based on the original diff and the generated diff.
 */
export async function gradeTask(originalDiffPath: string, generatedDiffPath: string): Promise<Grade> {
  const openaiClient = new OpenAI({
    baseURL: env.OPENAI_BASE || 'https://api.openai.com/v1',
    apiKey: env.OPENAI_API_KEY,
  });

  const originalDiff = await fs.readFile(originalDiffPath, 'utf8');
  const generatedDiff = await fs.readFile(generatedDiffPath, 'utf8');

  const instructions = `
  You are an expert evaluator of code changes. You are given two git diffs and a task description.

  An OriginalDiff -> A code diff written by a human.
  A GeneratedDiff -> A code diff written by a code generation model.
  The task description is the description of the task that the code generation model was asked to generate.

  You need to evaluate the semantic similarity of GeneratedDiff based on the OriginalDiff and the task description.
  You need to return a score between 0 and 5, where 5 is the highest score and 0 is the lowest score.
  ### Diffs to compare

  Original Diff:
  ${originalDiff}

  Generated Diff:
  ${generatedDiff}

  ### Evaluation Focus
  - Focus on the task implementation and whether the GeneratedDiff matches the OriginalDiff in terms of the task implementation.
  - Ignore code style, formatting, and other non-semantic changes.
  - Prioritise semantic intent and coverage of the task implementation.

  ### Scoring Rubric (1–5)
  - 1: The GeneratedDiff is not similar to the OriginalDiff at all.
  - 2: The GeneratedDiff is partially similar to the OriginalDiff.
  - 3: The GeneratedDiff is somewhat similar to the OriginalDiff.
  - 4: The GeneratedDiff is mostly similar to the OriginalDiff.
  - 5: The GeneratedDiff is exactly the same as the OriginalDiff.

  ### Output Format
    Return ONLY a valid JSON object:
    {
      "score": <integer 1-5>,
      "explanation": "<short, clear rationale (1–3 sentences)>"
    }
  `;

  if (originalDiff.trim().length === 0) {
    return {
      score: 0,
      explanation: 'The original diff is empty. Codex failed to generate a diff.',
    };
  }

  const response = await openaiClient.responses.parse({
    model: 'gpt-5',
    instructions: instructions,
    input: originalDiff,
    text: {
      format: zodTextFormat(GradeResult, 'gradeResult'),
    },
  });

  return response.output_parsed as Grade;
}
