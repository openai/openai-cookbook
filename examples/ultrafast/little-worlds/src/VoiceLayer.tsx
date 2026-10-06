import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import VoiceControls from './VoiceControls';
import { createLiveVoice } from './live-voice';
import type { LiveVoiceSnapshot, VoiceTranscript } from './live-voice';
import { createVoiceSurface, visibleForVoice, voiceScope } from './voice-surface';
import { canResumeVoice, saveVoiceResume, takeVoiceResume } from './voice-resume';
import type { VoiceResumeIntent } from './voice-resume';

export default function VoiceLayer({ identity, context, ready = true }: { identity: string | null; context: string; ready?: boolean }) {
  const [dock] = useState(() => document.createElement('div'));
  const [state, setState] = useState<LiveVoiceSnapshot>({ status: 'idle', connected: false, muted: false, speaking: false, working: false, audioBlocked: false, mutePending: false });
  const [levels, setLevels] = useState({ input: 0, output: 0 });
  const [transcript, setTranscript] = useState<VoiceTranscript[]>([]);
  const [resumeNotice, setResumeNotice] = useState<string>();
  const currentContext = useRef(context);
  const spoken = useRef('');
  const spokenTurns = useRef<VoiceTranscript[]>([]);
  const client = useRef<ReturnType<typeof createLiveVoice> | null>(null);
  const previousIdentity = useRef(identity);
  const currentIdentity = useRef(identity);
  const currentState = useRef(state);
  const pendingResume = useRef<VoiceResumeIntent | null>(null);
  const resumeMuted = useRef(false);
  currentContext.current = context;
  currentIdentity.current = identity;

  useEffect(() => {
    pendingResume.current = takeVoiceResume() || pendingResume.current;
    const surface = createVoiceSurface({ context: () => {
      const page = document.querySelector<HTMLElement>('[data-voice-context]')?.dataset.voiceContext || '';
      return `${currentContext.current}\n${page}`;
    }, userSpeech: () => spoken.current, userTurns: () => spokenTurns.current, voice: { stop: () => { void client.current?.stop(); }, mute: () => client.current?.setMuted(true) } });
    const voice = createLiveVoice({
      readSurface: surface.read, execute: surface.execute, onState: next => {
        if (next.status === 'idle' || next.status === 'error' || next.status === 'reconnecting') surface.clear();
        currentState.current = next;
        setState(next);
      },
      onTranscript: items => {
        setTranscript(items);
        spokenTurns.current = items;
        spoken.current = items.filter(item => item.role === 'user').map(item => item.text).join('\n');
      }, onLevel: setLevels,
    });
    client.current = {
      ...voice,
      start: async options => { surface.clear(); await voice.start(options); },
      resetConversation: () => { surface.clear(); voice.resetConversation(); },
    };
    const rememberLive = () => {
      const latest = currentState.current;
      const active = latest.status !== 'idle' && latest.status !== 'error';
      saveVoiceResume(active ? { identity: currentIdentity.current, muted: latest.muted, savedAt: Date.now() } : null);
    };
    const resumedPage = () => { takeVoiceResume(); };
    let timer: ReturnType<typeof setTimeout> | undefined;
    let lastContext = '';
    function positionDock() {
      const scope = voiceScope();
      if (dock.parentElement !== scope) scope.appendChild(dock);
      dock.className = `voice-dock${scope instanceof HTMLDialogElement ? ' voice-in-dialog' : ''}`;
      return scope;
    }
    function update() {
      const scope = positionDock();
      const page = document.querySelector<HTMLElement>('[data-voice-context]')?.dataset.voiceContext || '';
      const status = [...scope.querySelectorAll<HTMLElement>('[role="status"],[role="alert"]')]
        .filter(visibleForVoice)
        .map(node => node.innerText.trim()).filter(Boolean).join(' ').slice(0, 450);
      const dialog = scope === document.body ? '' : scope.querySelector('h1,h2')?.textContent || '';
      const draft = scope.querySelector<HTMLTextAreaElement>('.composer textarea')?.value;
      const summary = `${currentContext.current}. ${page} ${dialog ? `Open view: ${dialog}.` : ''} ${status} ${draft ? 'A builder draft is present. It has not been submitted by this context update.' : ''}`.slice(0, 1500);
      if (summary !== lastContext) { lastContext = summary; voice.updateContext(summary); }
    }
    // Move before the next paint when navigation replaces the current scope.
    // Only model context updates need debouncing, not the persistent controls.
    const schedule = () => { positionDock(); clearTimeout(timer); timer = setTimeout(update, 180); };
    const observer = new MutationObserver(records => {
      if (records.some(record => !(record.target instanceof Element ? record.target : record.target.parentElement)?.closest('[data-voice-ignore]'))) schedule();
    });
    dock.setAttribute('data-voice-ignore', '');
    document.body.classList.add('with-live-voice');
    update();
    observer.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['open', 'inert', 'data-voice-context'], characterData: true });
    document.addEventListener('input', schedule);
    window.addEventListener('popstate', schedule);
    window.addEventListener('pagehide', rememberLive);
    window.addEventListener('pageshow', resumedPage);
    return () => {
      rememberLive();
      observer.disconnect(); clearTimeout(timer);
      document.removeEventListener('input', schedule); window.removeEventListener('popstate', schedule);
      window.removeEventListener('pagehide', rememberLive); window.removeEventListener('pageshow', resumedPage);
      surface.clear(); voice.destroy(); client.current = null;
      dock.remove(); document.body.classList.remove('with-live-voice');
    };
  }, [dock]);
  useEffect(() => { client.current?.updateContext(context); }, [context]);
  useEffect(() => {
    if (!ready) return;
    if (previousIdentity.current && previousIdentity.current !== identity) {
      pendingResume.current = null; resumeMuted.current = false; saveVoiceResume(null); setResumeNotice(undefined);
      if (identity) client.current?.resetConversation();
      else void client.current?.stop();
      setTranscript([]); spoken.current = ''; spokenTurns.current = [];
    }
    previousIdentity.current = identity;
  }, [identity, ready]);
  useEffect(() => {
    const intent = pendingResume.current;
    if (!ready || !intent) return;
    let cancelled = false;
    const voice = client.current;
    if (intent.identity !== identity) { pendingResume.current = null; return; }
    void canResumeVoice(intent, identity).then(allowed => {
      if (cancelled || client.current !== voice || pendingResume.current !== intent) return;
      pendingResume.current = null;
      if (allowed) void voice?.start({ muted: intent.muted });
      else {
        resumeMuted.current = intent.muted;
        setResumeNotice('Your page reloaded. Tap Go live to resume your conversation.');
      }
    });
    return () => { cancelled = true; };
  }, [identity, ready, dock]);
  const userCaption = transcript.filter(item => item.role === 'user').at(-1)?.text || '';
  const assistantCaption = transcript.filter(item => item.role === 'assistant').at(-1)?.text || '';
  return createPortal(<VoiceControls status={state.status} muted={state.muted} inputLevel={levels.input} outputLevel={levels.output}
    userCaption={userCaption} assistantCaption={assistantCaption} error={state.error || null} notice={state.notice || resumeNotice} mutePending={state.mutePending} playbackBlocked={state.audioBlocked}
    onStart={() => { pendingResume.current = null; setResumeNotice(undefined); spoken.current = ''; spokenTurns.current = []; setTranscript([]); void client.current?.start({ muted: resumeMuted.current }); resumeMuted.current = false; }}
    onStop={() => { pendingResume.current = null; saveVoiceResume(null); setResumeNotice(undefined); void client.current?.stop(); }}
    onToggleMute={() => client.current?.setMuted(!state.muted)} onResumeAudio={() => { void client.current?.resumeAudio(); }}/>, dock);
}
