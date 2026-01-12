import { spawn } from 'node:child_process';

export function diffWorktreeStream(worktreeDir: string, args: string[] = []): Promise<string> {
  const cli = ['-C', worktreeDir, 'diff', '--no-color', ...args];

  return new Promise((resolve, reject) => {
    const ps = spawn('git', cli, { stdio: ['ignore', 'pipe', 'pipe'] });

    const stdoutChunks: Buffer[] = [];
    const stderrChunks: Buffer[] = [];

    ps.stdout.on('data', (chunk: Buffer) => stdoutChunks.push(chunk));
    ps.stderr.on('data', (chunk: Buffer) => stderrChunks.push(chunk));

    ps.on('error', reject);
    ps.on('close', (code) => {
      if (code === 0) {
        resolve(Buffer.concat(stdoutChunks).toString('utf8'));
      } else {
        reject(new Error(`git diff exited ${code}: ${Buffer.concat(stderrChunks).toString('utf8')}`));
      }
    });
  });
}

export function runGitCapture(args: string[], cwd: string): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const ps = spawn('git', args, { cwd, stdio: ['ignore', 'pipe', 'pipe'] });
    const stdoutChunks: Buffer[] = [];
    const stderrChunks: Buffer[] = [];
    ps.stdout.on('data', (c: Buffer) => stdoutChunks.push(c));
    ps.stderr.on('data', (c: Buffer) => stderrChunks.push(c));
    ps.on('error', reject);
    ps.on('close', (code) => {
      if (code === 0) {
        resolve(Buffer.concat(stdoutChunks).toString('utf8').trim());
      } else {
        reject(new Error(`git ${args.join(' ')} exited ${code}: ${Buffer.concat(stderrChunks).toString('utf8')}`));
      }
    });
  });
}

export async function resolveBaseCommitFromCommitHash(repoDir: string, commitHash: string): Promise<{ mergedCommit: string; baseCommit: string }>{
  const mergedCommit = await runGitCapture(['rev-parse', commitHash], repoDir);
  if (!mergedCommit) {
    throw new Error(`Could not resolve commit ${commitHash}. Ensure the repository has the commit locally.`);
  }
  const baseCommit = await runGitCapture(['rev-parse', `${mergedCommit}^`], repoDir);
  return { mergedCommit, baseCommit };
}

export function addWorktree(workTreeName: string, repoDir: string, commitish?: string): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    const args = commitish ? ['worktree', 'add', '--detach', workTreeName, commitish] : ['worktree', 'add', workTreeName];
    const ps = spawn('git', args, {
      cwd: repoDir,
      stdio: 'inherit',
    });
    ps.on('close', (code) => (code === 0 ? resolve() : reject(new Error(`git exited ${code}`))));
  });
}

export function deleteWorktree(workTreeName: string, repoDir: string): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    const ps = spawn('git', ['worktree', 'remove', workTreeName, '--force'], {
      cwd: repoDir,
      stdio: 'inherit',
    });
    ps.on('close', (code) => (code === 0 ? resolve() : reject(new Error(`git exited ${code}`))));
  });
}
