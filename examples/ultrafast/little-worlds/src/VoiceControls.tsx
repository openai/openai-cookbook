import { useEffect, useId, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import { ChevronDown, Mic, MicOff, RotateCcw, Square, Volume2, X } from 'lucide-react';
import './voice.css';

export type VoiceControlsProps = {
  status: string;
  muted: boolean;
  inputLevel: number;
  outputLevel: number;
  userCaption: string;
  assistantCaption: string;
  error: string | null;
  notice?: string;
  mutePending?: boolean;
  playbackBlocked: boolean;
  onStart: () => void;
  onStop: () => void;
  onToggleMute: () => void;
  onResumeAudio: () => void;
};

const STATUS_LABELS: Record<string, string> = {
  idle: 'Go live',
  connecting: 'Connecting…',
  reconnecting: 'Reconnecting…',
  listening: 'Listening',
  working: 'Making it happen',
  speaking: 'Speaking',
  muted: 'Mic muted',
  error: 'Try voice again',
  closing: 'Ending…',
};

function boundedLevel(value: number) {
  return Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0;
}

/** A presentational control. Session and microphone ownership stay with the host. */
export default function VoiceControls({
  status, muted, inputLevel, outputLevel, userCaption, assistantCaption, error, notice, mutePending,
  playbackBlocked, onStart, onStop, onToggleMute, onResumeAudio,
}: VoiceControlsProps) {
  const [expanded, setExpanded] = useState(false);
  const widget = useRef<HTMLElement>(null);
  const panelId = useId();
  const headingId = useId();
  const canStart = status === 'idle' || status === 'error';
  const connecting = status === 'connecting';
  const reconnecting = status === 'reconnecting';
  const closing = status === 'closing';
  const connected = !canStart && !connecting && !reconnecting && !closing;
  const microphoneMuted = muted || status === 'muted';
  const label = connected && microphoneMuted && status !== 'speaking' && status !== 'working'
    ? STATUS_LABELS.muted
    : STATUS_LABELS[status] || 'Voice is live';
  const level = Math.max(microphoneMuted ? 0 : boundedLevel(inputLevel), boundedLevel(outputLevel));
  const orbStyle = { '--voice-level': level } as CSSProperties;

  useEffect(() => {
    // Routine voice updates are spoken and available in the conversation.
    // Only a stopped connection or blocked audio needs to open this panel.
    if (error || playbackBlocked) setExpanded(true);
  }, [error, playbackBlocked]);

  useEffect(() => {
    if (!expanded) return;
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !widget.current?.contains(event.target)) setExpanded(false);
    };
    document.addEventListener('pointerdown', closeOutside);
    return () => document.removeEventListener('pointerdown', closeOutside);
  }, [expanded]);

  return (
    <section
      ref={widget}
      className={`voice-controls${connected ? ' is-live' : ''}${microphoneMuted ? ' is-muted' : ''}${expanded ? ' is-expanded' : ''}`}
      data-status={status}
      data-voice-ignore="true"
      aria-label="Live voice controls"
      style={orbStyle}
      onKeyDown={event => {
        if (event.key === 'Escape' && expanded) {
          event.preventDefault();
          event.stopPropagation();
          setExpanded(false);
          widget.current?.querySelector<HTMLButtonElement>('.voice-primary')?.focus({ preventScroll: true });
        }
      }}
    >
      <div className="voice-pill">
        <button
          type="button"
          className="voice-primary"
          aria-label={canStart ? (status === 'error' ? 'Try live voice again' : 'Start live voice') : 'Show live voice conversation'}
          aria-expanded={canStart ? undefined : expanded}
          aria-controls={canStart ? undefined : panelId}
          title={notice || undefined}
          disabled={closing}
          onClick={() => {
            if (canStart) onStart();
            else setExpanded(value => !value);
          }}
        >
          <span className="voice-orb-shell" aria-hidden="true"><span className="voice-orb"><span /></span></span>
          <span className="voice-label">{label}</span>
          {connected && <span className="voice-live-mark" aria-hidden="true">LIVE</span>}
          {!canStart && !closing && <ChevronDown className="voice-chevron" size={12} aria-hidden="true" />}
          {status === 'error' && <RotateCcw size={13} aria-hidden="true" />}
        </button>

        {canStart && <button
          type="button"
          className="voice-icon-button voice-details-button"
          aria-label="About live voice"
          aria-expanded={expanded}
          aria-controls={panelId}
          title="About live voice"
          onClick={() => setExpanded(value => !value)}
        ><ChevronDown className="voice-chevron" size={14} aria-hidden="true" /></button>}

        {playbackBlocked && <button
          type="button"
          className="voice-icon-button voice-enable-sound"
          aria-label="Enable voice sound"
          title="Enable sound"
          onClick={onResumeAudio}
        ><Volume2 size={16} aria-hidden="true" /></button>}

        {(connected || reconnecting) && <button
          type="button"
          className={`voice-icon-button voice-mute-button${microphoneMuted ? ' is-selected' : ''}`}
          aria-label={microphoneMuted ? 'Unmute microphone' : 'Mute microphone'}
          aria-pressed={microphoneMuted}
          disabled={mutePending}
          title={microphoneMuted ? 'Unmute microphone' : 'Mute microphone'}
          onClick={onToggleMute}
        >{microphoneMuted ? <MicOff size={15} aria-hidden="true" /> : <Mic size={15} aria-hidden="true" />}</button>}

        {!canStart && <button
          type="button"
          className="voice-icon-button voice-end-button"
          aria-label={connecting ? 'Cancel voice connection' : 'End live voice'}
          title={connecting ? 'Cancel connection' : 'End voice'}
          disabled={closing}
          onClick={onStop}
        >{connecting ? <X size={16} aria-hidden="true" /> : <Square size={11} fill="currentColor" aria-hidden="true" />}</button>}
      </div>

      <span className="voice-sr-only" role="status" aria-live="polite" aria-atomic="true">
        {canStart ? (status === 'error' ? 'Live voice is disconnected.' : 'Live voice is off.') : label}{notice ? `. ${notice}` : ''}
      </span>

      {expanded && <div className="voice-panel" id={panelId} role="region" aria-labelledby={headingId}>
        <div className="voice-panel-heading">
          <div>
            <span className="voice-eyebrow">A LITTLE MORE HANDS-FREE</span>
            <h2 id={headingId}>{canStart ? 'Your space, in conversation.' : 'We’re in conversation.'}</h2>
          </div>
          <button type="button" className="voice-icon-button" aria-label="Close voice details" onClick={() => setExpanded(false)}><X size={15} aria-hidden="true" /></button>
        </div>

        {error && <div className="voice-notice voice-error" role="alert">
          <p>{error}</p>
          {canStart && <button type="button" onClick={onStart}><RotateCcw size={13} aria-hidden="true" />Try again</button>}
        </div>}

        {notice && !error && <div className="voice-notice" role="status"><p>{notice}</p></div>}
        {playbackBlocked && <div className="voice-notice">
          <p>Your browser needs a tap to play the conversation.</p>
          <button type="button" onClick={onResumeAudio}><Volume2 size={14} aria-hidden="true" />Enable sound</button>
        </div>}

        {(userCaption || assistantCaption) && !canStart ? <div className="voice-captions" aria-label="Latest conversation">
          {userCaption && <div className="voice-caption voice-caption-user"><span>You</span><p>{userCaption}</p></div>}
          {assistantCaption && <div className="voice-caption voice-caption-assistant"><span>Little Worlds</span><p>{assistantCaption}</p></div>}
        </div> : <div className="voice-welcome">
          <p>{reconnecting ? 'Live is restoring your connection. Your microphone setting will stay the same.' : connecting ? 'Allow microphone access to get started.' : connected ? 'Say what you have in mind. You can interrupt anytime.' : 'Explore, describe an idea, or make a change with your voice.'}</p>
          <div className="voice-examples" aria-label="Things to try saying"><span>“Show me the community”</span><span>“Make my space feel like a garden”</span></div>
        </div>}

        <div className="voice-panel-footer">
          {connected && microphoneMuted ? <MicOff size={13} aria-hidden="true" /> : <Mic size={13} aria-hidden="true" />}
          <p>{reconnecting ? `${microphoneMuted ? 'Your microphone will stay muted.' : 'Live will resume listening when connected.'} You can keep typing and clicking.` : connected
            ? microphoneMuted ? 'Your microphone is muted. You can still type and click.' : 'Your microphone is on. Mute or end anytime, and keep typing or clicking as usual.'
            : 'When live, your microphone stays on until you mute or end. You can still type and click.'}</p>
        </div>
      </div>}
    </section>
  );
}
