import { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import GeneratedFrame from '../../src/GeneratedFrame';
import type { FrameGameSource } from '../../src/GeneratedFrame';
import { getVoiceFrame } from '../../src/voice-frame-registry';
import type { GameConfig, GameActor, GameState } from '../../shared/game-schema.mjs';
import { ArcadeLayoutProbe, arcadeAppearance } from './arcade-layout';

type FixtureGame = { name: string; config: GameConfig; bundle: string; saved: GameState };
type Fixture = { revisionId: number; sourceKind?: string; actor: GameActor; html: string; games: FixtureGame[] };
type Checkpoint = { loads: number; saves: number; game: GameState };
const presentation = new URLSearchParams(window.location.search).has('presentation');

function summary(state: GameState) {
  const values = Object.fromEntries(['actorId', 'score', 'lives', 'wave', 'level', 'lines', 'pieces', 'status', 'ready', 'finished', 'over', 'direction', 'queued', 'player', 'playerNext', 'playerProgress', 'playerX', 'input', 'piece'].filter(key => state[key] !== undefined).map(key => [key, state[key]]));
  for (const key of ['body', 'pellets', 'aliens', 'shots', 'enemyShots']) {
    if (Array.isArray(state[key])) {
      values[`${key}Count`] = state[key].length;
      if (key === 'body') values.head = state[key][0];
    }
  }
  return JSON.stringify(values);
}

function Arcade({ fixture }: { fixture: Fixture }) {
  const [theme, setTheme] = useState<'light' | 'dark'>('dark');
  const [pending, setPending] = useState(false);
  const [revision, setRevision] = useState(fixture.revisionId);
  const [mounted, setMounted] = useState(true);
  const [isolationError, setIsolationError] = useState('');
  const saved = useRef(new Map(fixture.games.map(game => [game.config.id, structuredClone(game.saved)])));
  const [checkpoints, setCheckpoints] = useState<Record<string, Checkpoint>>(() => Object.fromEntries(fixture.games.map(game => [game.config.id, { loads: 0, saves: 0, game: game.saved }])));
  const [voiceResult, setVoiceResult] = useState({ status: 'idle', target: 'none', message: 'No voice action yet.' });
  const voiceInFlight = useRef(false);
  const games = useMemo<FrameGameSource[]>(() => fixture.games.map(game => ({
    id: game.config.id,
    async load() {
      setCheckpoints(current => ({ ...current, [game.config.id]: { ...current[game.config.id], loads: current[game.config.id].loads + 1 } }));
      return { revisionId: revision, actor: fixture.actor, config: game.config, bundle: game.bundle, saved: structuredClone(saved.current.get(game.config.id) ?? null) };
    },
    async save(action) {
      if (action.type !== game.config.saveAction || action.game.actorId !== fixture.actor.id) {
        setIsolationError(`Unexpected checkpoint for ${game.config.id}.`);
        return false;
      }
      const next = structuredClone(action.game);
      saved.current.set(game.config.id, next);
      setCheckpoints(current => ({ ...current, [game.config.id]: { ...current[game.config.id], saves: current[game.config.id].saves + 1, game: next } }));
      return true;
    },
  })), [fixture, revision]);

  const voiceAction = async (game: FixtureGame, label: string) => {
    if (voiceInFlight.current) return;
    voiceInFlight.current = true;
    let target = `${game.config.id}: ${label}`;
    setVoiceResult({ status: 'pending', target, message: 'Reading the real registered voice controls…' });
    try {
      const frame = getVoiceFrame();
      if (!frame) throw new Error('No published voice frame is registered.');
      const surface = await frame.read();
      const matches = surface.controls.filter(control => control.role === 'button' && control.label === label &&
        [game.name, game.config.id].some(name => control.context?.toLowerCase().includes(name.toLowerCase())));
      if (matches.length !== 1) throw new Error(`Expected one ${label} control in ${game.name}; found ${matches.length}.`);
      const control = matches[0];
      target = `${game.config.id}: ${control.label} [${control.id}] (${control.context})`;
      const result = await frame.execute({ type: 'click', id: control.id }, surface.version);
      setVoiceResult({ status: result.ok ? 'success' : 'error', target, message: result.message });
    } catch (error) {
      setVoiceResult({ status: 'error', target, message: error instanceof Error ? error.message : String(error) });
    } finally { voiceInFlight.current = false; }
  };

  return <main className={`fixture${presentation ? ' presentation-fixture' : ''}`} style={presentation ? { colorScheme: theme } : undefined}>
    <h1>Actual arcade browser verification</h1>
    <p>Compiled from <code>{fixture.sourceKind === 'prepared' ? 'the current prepared source with fresh fixture state' : 'arcadeProposal()'}</code>, using the production frame, game controller, public game bundles and voice registry. No real saves or model calls are involved. All checkpoints stay in memory.</p>
    <p id="arcade-fixture-state">Revision: {revision}. Draft: {String(pending)}. Mounted: {String(mounted)}. Games: {games.length}.</p>
    <div>
      <button onClick={() => setPending(value => !value)}>{pending ? 'Show published' : 'Show draft'}</button>
      <button onClick={() => setRevision(value => value + 1)}>Change revision</button>
      <button onClick={() => setMounted(value => !value)}>{mounted ? 'Remove frame' : 'Restore frame'}</button>
      {presentation && <button onClick={() => setTheme(value => value === 'dark' ? 'light' : 'dark')}>Switch to {theme === 'dark' ? 'light' : 'dark'} mode</button>}
    </div>
    {presentation && <ArcadeLayoutProbe html={fixture.html} />}
    <details>
      <summary>In-memory checkpoints</summary>
      <p id="arcade-isolation-state">{isolationError || 'No invalid checkpoint requests.'}</p>
      {fixture.games.map(game => <article key={game.config.id} id={`arcade-record-${game.config.id}`}>
        <h2>{game.name}</h2>
        <p>Loads: <span data-field="loads">{checkpoints[game.config.id].loads}</span>. Saves: <span data-field="saves">{checkpoints[game.config.id].saves}</span>.</p>
        <pre data-field="state">{summary(checkpoints[game.config.id].game)}</pre>
      </article>)}
    </details>
    <details>
      <summary>Voice control verification without a model</summary>
      <p>Each button reads the current published surface, matches the game context, and uses its real voice target. Pointer activation preserves game focus.</p>
      {fixture.games.map(game => <div key={game.config.id} className="voice-row">
        {['Start', 'Pause', 'Resume', 'Restart'].map(command => <button key={command} onPointerDown={event => event.preventDefault()} onClick={() => void voiceAction(game, `${command} ${game.name}`)}>Voice {command.toLowerCase()} {game.name}</button>)}
        {['move left', ...(game.config.id === 'space-invaders' ? ['fire'] : game.config.id === 'tetris' ? ['rotate', 'drop'] : ['move up', 'move right'])].map(command => <button key={command} onPointerDown={event => event.preventDefault()} onClick={() => void voiceAction(game, `${game.name} ${command}`)}>Voice {game.name} {command}</button>)}
      </div>)}
      <p id="arcade-voice-state" role="status" data-status={voiceResult.status} data-target={voiceResult.target}>Status: {voiceResult.status}. Target: {voiceResult.target}. Result: {voiceResult.message}</p>
    </details>
    {mounted && <GeneratedFrame html={fixture.html} appearance={presentation ? arcadeAppearance : undefined} games={games} revisionId={revision} renderVersion={revision} pending={pending} onAction={async () => ({ ok: false })} />}
  </main>;
}

function App() {
  const [fixture, setFixture] = useState<Fixture | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    void fetch('./.generated/karen.json').then(async response => {
      if (!response.ok) throw new Error('Run node scripts/build-arcade-fixture.mjs to build the local fixture first.');
      return response.json() as Promise<Fixture>;
    }).then(value => { if (active) setFixture(value); }).catch(failure => { if (active) setError(String(failure)); });
    return () => { active = false; };
  }, []);
  return <>
    <style>{`body{margin:0;background:#f4f1e9;color:#24251e;font-family:system-ui,sans-serif}.fixture{max-width:1180px;margin:24px auto;padding:0 20px}.fixture>h1{font-size:24px}.fixture>p{font-size:13px;line-height:1.6}.fixture button{padding:7px 10px;margin:3px;border:1px solid #bbb;border-radius:5px;background:#fff;color:#24251e;cursor:pointer}.fixture details{border:1px solid #d8d6cd;border-radius:7px;padding:10px;margin:10px 0;font-size:13px}.fixture summary{cursor:pointer}.fixture pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}.fixture article h2{font-size:15px}.generated-frame{display:block;width:100%;border:0;margin-top:20px}.voice-row{padding:4px 0;border-bottom:1px solid #ddd}`}</style>
    {presentation && <style>{`.presentation-fixture{position:relative;width:90%;max-width:calc(1640 * clamp(.75px,100vw / 1920,2px));padding:0}.arcade-layout-mirror{position:absolute;left:-100000px;top:0;width:100%;height:12000px;border:0;pointer-events:none}.layout-report{max-height:320px;overflow:auto}`}</style>}
    {fixture ? <Arcade fixture={fixture} /> : <main className="fixture"><h1>Actual arcade browser verification</h1><p role="status">{error || 'Loading compiled arcade fixture…'}</p></main>}
  </>;
}

createRoot(document.getElementById('root')!).render(<App />);
