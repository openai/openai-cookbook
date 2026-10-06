import type { ThroughputReading } from './build-throughput';
import { BUILD_SPEEDOMETER_MAX_TPS, speedometerPosition } from './build-speedometer-geometry';

export function BuildSpeedometer({ rate, mode }: ThroughputReading) {
  const available = rate !== null;
  const value = available ? Math.round(rate).toLocaleString() : '—';
  const average = mode === 'complete';
  const label = average ? 'avg tps' : 'live tps';
  const description = mode === 'disconnected' ? 'Reconnecting. Live output speed is unavailable.'
    : !available ? 'Output speed is unavailable for this request.'
    : `${average ? 'Average' : 'Live'} visible output: approximately ${value} tokens per second. Estimated with a local tokenizer from incoming text and code, excluding private reasoning. ${average ? 'Average over output delivery, excluding the initial wait and tool execution.' : 'Recent output arrivals.'} The needle scale is 0 to ${BUILD_SPEEDOMETER_MAX_TPS.toLocaleString()} tokens per second.`;
  const position = speedometerPosition(rate);
  return <div className="build-tps-metric" title={description}>
    <div className={`build-speedometer is-${mode}`} role="img" aria-label={description} data-rate={available ? Math.round(rate) : ''} data-mode={mode} data-max-rate={BUILD_SPEEDOMETER_MAX_TPS}>
      <svg viewBox="0 0 60 32" aria-hidden="true">
        <path className="build-speed-track" d="M 6 28 A 24 24 0 0 1 54 28" pathLength="100"/>
        <path className="build-speed-fill" d="M 6 28 A 24 24 0 0 1 54 28" pathLength="100" strokeDasharray="100 100" strokeDashoffset={position.dashOffset}/>
        <g className="build-speed-needle" style={{ transform: `rotate(${position.rotation}deg)`, transformOrigin: '30px 28px' }}>
          <path d="M 28.5 28 L 30 8 L 31.5 28 Z"/>
          <circle cx="30" cy="28" r="2"/>
        </g>
      </svg>
      <strong aria-hidden="true">{available && rate > 0 && <small>≈</small>}{value}</strong>
    </div>
    <span className="build-tps-unit" aria-hidden="true">{label}</span>
  </div>;
}
