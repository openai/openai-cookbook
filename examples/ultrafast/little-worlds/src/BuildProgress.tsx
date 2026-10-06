import { useState } from 'react';
import './build-progress.css';

export type BuildProgressProps = {
  status: 'pending' | 'ready' | 'fallback';
  expectedOutputTokens?: number;
  outputTokens: number;
  laneStatus: 'preparing' | 'running' | 'completed' | 'failed' | 'cancelled';
  tier: 'ultrafast' | 'standard';
  /** Final visible output from a successful Ultrafast run in this comparison. */
  completedReferenceTokens?: number;
  phase?: 'build' | 'verify' | 'publish';
};

type ProgressInput = Pick<BuildProgressProps, 'status' | 'expectedOutputTokens' | 'outputTokens' | 'laneStatus' | 'phase'>;

function validEstimate(value: number | undefined): number | undefined {
  return value !== undefined && Number.isFinite(value) && value > 0 ? value : undefined;
}

function validOutput(value: number): number {
  return Number.isFinite(value) && value > 0 ? value : 0;
}

/** Token estimates reserve the final fill for an actual successful completion. */
export function deriveBuildProgress({ status, expectedOutputTokens, outputTokens, laneStatus, phase }: ProgressInput) {
  const estimate = status === 'pending' ? undefined : validEstimate(expectedOutputTokens);
  const terminal = laneStatus === 'completed' || laneStatus === 'failed' || laneStatus === 'cancelled';
  // These are actual harness milestones, not guessed elapsed-time progress.
  const phaseFloor = phase === 'publish' ? .97 : phase === 'verify' ? .9 : 0;
  const indeterminate = !terminal && estimate === undefined && phaseFloor === 0;
  const ratio = estimate === undefined ? 0 : validOutput(outputTokens) / estimate;
  const value = laneStatus === 'completed' ? 1
    : Math.max(phaseFloor, ratio <= 1 ? .9 * ratio : .9 + .05 * (1 - Math.exp(-(ratio - 1))));
  const state = terminal ? laneStatus : indeterminate ? 'pending' : 'active';
  return { value, indeterminate, state };
}

/** Remount for each comparison; only its successful peer may replace the guess. */
export default function BuildProgress({ status, expectedOutputTokens, outputTokens, laneStatus, tier, completedReferenceTokens, phase }: BuildProgressProps) {
  const candidate = status === 'pending' ? undefined : validEstimate(expectedOutputTokens);
  const referenceCandidate = tier === 'standard' && (laneStatus === 'preparing' || laneStatus === 'running')
    ? validEstimate(completedReferenceTokens) : undefined;
  const [accepted, setAccepted] = useState(() => ({
    initialEstimate: candidate, reference: referenceCandidate, output: validOutput(outputTokens), completed: laneStatus === 'completed', value: 0,
  }));
  const initialEstimate = accepted.initialEstimate ?? candidate;
  // Final telemetry can arrive after completion. Retain the fullest observed
  // reference, including across replay, without ever moving the visible bar back.
  const reference = Math.max(accepted.reference ?? 0, referenceCandidate ?? 0) || undefined;
  const estimate = reference ?? initialEstimate;
  const output = Math.max(accepted.output, validOutput(outputTokens));
  const completed = accepted.completed || laneStatus === 'completed';
  const progress = deriveBuildProgress({
    status: estimate === undefined ? status : 'ready', expectedOutputTokens: estimate, outputTokens: output, phase,
    laneStatus: completed && (laneStatus === 'preparing' || laneStatus === 'running') ? 'completed' : laneStatus,
  });
  const value = Math.max(accepted.value, progress.value);
  // Hold earned progress through repairs, replays, and a larger calibrated
  // budget. CSS eases forward to the new target rather than snapping the fill.
  if (initialEstimate !== accepted.initialEstimate || reference !== accepted.reference || output !== accepted.output || completed !== accepted.completed || value !== accepted.value) {
    setAccepted({ initialEstimate, reference, output, completed, value });
  }
  const indeterminate = progress.indeterminate && value === 0;
  const label = tier === 'ultrafast' ? 'Ultrafast' : 'Standard';
  const valueText = progress.state === 'completed' ? 'Build complete'
    : progress.state === 'failed' ? 'Build failed'
    : progress.state === 'cancelled' ? 'Build stopped'
    : indeterminate ? 'Waiting for a build estimate'
    : `Estimated progress: ${Math.round(value * 100)}%`;

  return <div className="build-progress" data-tier={tier} data-progress-state={progress.state === 'pending' && !indeterminate ? 'active' : progress.state} data-estimator-status={status} data-expected-output-tokens={estimate} data-progress-basis={reference ? 'ultrafast' : estimate ? 'estimate' : 'pending'}
    title={reference ? 'Calibrated from the completed Ultrafast build. Output lengths can differ; full means the build succeeded.' : 'Based on streamed output and build milestones. Full means the build succeeded.'}>
    <div className="build-progress-heading">Build progress</div>
    <div className="build-progress-track" role="progressbar" aria-label={`${label} build progress`} aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={indeterminate ? undefined : Math.round(value * 100)} aria-valuetext={valueText}>
      <div className="build-progress-fill" style={{ transform: `scaleX(${value})` }}/>
      {indeterminate && <div className="build-progress-highlight"/>}
    </div>
  </div>;
}
