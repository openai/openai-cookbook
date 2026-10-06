import { useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import GeneratedFrame from '../../src/GeneratedFrame';
import type { FrameGameSource } from '../../src/GeneratedFrame';
import { getVoiceFrame } from '../../src/voice-frame-registry';
import type { GameState } from '../../shared/game-schema.mjs';

const actor = { id: 'fixture', name: 'Browser fixture' };
const definitions = [
  { id: 'movingdot', name: 'Moving dot', color: '#e3c55b', background: '#102333', speed: 2, start: 30, ticks: 0 },
  { id: 'orbit', name: 'Blue orbit', color: '#73d0e6', background: '#183749', speed: 3, start: 70, ticks: 100 },
  { id: 'runner', name: 'Coral runner', color: '#ef9d82', background: '#452d39', speed: 4, start: 110, ticks: 200 },
  { id: 'slider', name: 'Green slider', color: '#acd49a', background: '#263d37', speed: 5, start: 150, ticks: 300 },
] as const;
type GameId = typeof definitions[number]['id'];
type GameDefinition = typeof definitions[number];
type RecordReadout = { checkpoints: number; loads: number; game: GameState };

function initialState(definition: GameDefinition): GameState {
  return { actorId: actor.id, fixtureGame: definition.id, ticks: definition.ticks, x: definition.start, direction: 1, held: 'none', presses: 0, releases: 0 };
}

function bundleFor(definition: GameDefinition) {
  return `var GameModule = { game: {
    init(saved, actor) { return saved ? {...saved, held:'none'} : {actorId:actor.id,fixtureGame:'${definition.id}',ticks:0,x:${definition.start},direction:1,held:'none',presses:0,releases:0}; },
    step(state, action) {
      if(action.type==='tick') {
        const direction = state.held==='left'?-1:state.held==='right'?1:state.direction;
        return {...state,ticks:state.ticks+1,x:(state.x+direction*${definition.speed}+240)%240};
      }
      if(action.type==='direction') return {...state,direction:action.direction==='left'?-1:1};
      if(action.type==='input' && (action.key==='left'||action.key==='right')) return action.held
        ? {...state,held:action.key,presses:state.presses+1}
        : {...state,held:state.held===action.key?'none':state.held,releases:state.releases+1};
      throw new Error('Unknown action');
    },
    view(state) {
      return {width:260,height:140,background:'${definition.background}',objects:[
        {id:'player',type:'circle',x:state.x+10,y:70,radius:12,fill:'${definition.color}'}
      ],values:{game:state.fixtureGame,ticks:state.ticks,x:state.x,direction:state.direction<0?'left':'right',held:state.held,presses:state.presses,releases:state.releases}};
    }
  } };`;
}

function tileHtml(definition: GameDefinition) {
  return `<section data-game="${definition.id}" tabindex="0" aria-label="${definition.name} game">
    <h2>${definition.name}</h2>
    <canvas data-game-canvas aria-label="${definition.name} arena" width="260" height="140"></canvas>
    <p>Game: <span data-game-value="game">${definition.id}</span>. Ticks: <span data-game-value="ticks">${definition.ticks}</span>. Position: <span data-game-value="x">${definition.start}</span>.</p>
    <p>Direction: <span data-game-value="direction">right</span>. Held: <span data-game-value="held">none</span>. Presses: <span data-game-value="presses">0</span>. Releases: <span data-game-value="releases">0</span>.</p>
    <p data-game-runtime-status role="status">Ready to play.</p>
    <div aria-label="${definition.name} lifecycle controls">
      <button data-game-command="start">Start ${definition.name}</button>
      <button data-game-command="pause">Pause ${definition.name}</button>
      <button data-game-command="resume">Resume ${definition.name}</button>
      <button data-game-command="restart">New ${definition.name}</button>
    </div>
    <div aria-label="${definition.name} direction controls">
      <button data-game-action='{"type":"direction","direction":"left"}'>Move left</button>
      <button data-game-action='{"type":"direction","direction":"right"}'>Move right</button>
      <button data-game-action='{"type":"input","key":"left","held":true}' data-game-release='{"type":"input","key":"left","held":false}' data-game-keys="ArrowLeft a A">Hold left</button>
      <button data-game-action='{"type":"input","key":"right","held":true}' data-game-release='{"type":"input","key":"right","held":false}' data-game-keys="ArrowRight d D">Hold right</button>
    </div>
    <label>Typing guard <input aria-label="${definition.name} typing guard" placeholder="Arrow keys here must not steer"></label>
  </section>`;
}

const frameStyle = `<style>
  .arcade{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:16px;padding:4px}
  section{min-width:0;padding:20px;background:#eef1e6;border-radius:18px}
  section:focus{outline:2px solid #658453;outline-offset:1px}
  h2{font-size:20px;margin:0 0 14px}canvas{display:block;width:100%;border-radius:12px}
  button{margin:3px;padding:8px 10px}p{margin:10px 0}label{display:block;margin-top:12px}input{display:block;width:100%;padding:8px;margin-top:4px}
</style>`;

function App() {
  const [mounted, setMounted] = useState(true);
  const [pending, setPending] = useState(false);
  const [multiple, setMultiple] = useState(true);
  const [revision, setRevision] = useState(1);
  const [removed, setRemoved] = useState<ReadonlySet<GameId>>(new Set());
  const [failure, setFailure] = useState('');
  const [voiceBusy, setVoiceBusy] = useState(false);
  const voiceInFlight = useRef(false);
  const [voiceResult, setVoiceResult] = useState({ status: 'idle', target: 'none', message: 'No voice action yet.' });
  const saved = useRef(new Map<GameId, GameState>(definitions.map(definition => [definition.id, initialState(definition)])));
  const [records, setRecords] = useState(() => Object.fromEntries(definitions.map(definition => [definition.id, {
    checkpoints: 0, loads: 0, game: initialState(definition),
  }])) as Record<GameId, RecordReadout>);
  const games = useMemo<FrameGameSource[]>(() => definitions.map(definition => ({
    id: definition.id,
    async load() {
      setRecords(current => ({ ...current, [definition.id]: { ...current[definition.id], loads: current[definition.id].loads + 1 } }));
      return {
        revisionId: revision,
        config: { id: definition.id, tickMs: 50, saveAction: `checkpoint_${definition.id}` },
        actor, bundle: bundleFor(definition), saved: structuredClone(saved.current.get(definition.id) ?? null),
      };
    },
    async save(action) {
      if (action.type !== `checkpoint_${definition.id}` || action.game.fixtureGame !== definition.id) {
        setFailure(`Cross-game checkpoint rejected for ${definition.id}.`);
        return false;
      }
      const game = structuredClone(action.game);
      saved.current.set(definition.id, game);
      setRecords(current => ({ ...current, [definition.id]: { ...current[definition.id], checkpoints: current[definition.id].checkpoints + 1, game } }));
      return true;
    },
  })), [revision]);
  const activeDefinitions = useMemo(() => (multiple ? definitions : definitions.slice(0, 1)).filter(definition => !removed.has(definition.id)), [multiple, removed]);
  const activeGames = useMemo(() => games.filter(game => activeDefinitions.some(definition => definition.id === game.id)), [games, activeDefinitions]);
  const html = useMemo(() => `${frameStyle}<div class="arcade">${activeDefinitions.map(tileHtml).join('')}</div>`, [activeDefinitions]);
  const toggleGame = (id: GameId) => setRemoved(current => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const checkpointCount = definitions.reduce((total, definition) => total + records[definition.id].checkpoints, 0);
  const voiceAction = async (definition: GameDefinition, action: 'start' | 'left') => {
    if (voiceInFlight.current) return;
    voiceInFlight.current = true;
    setVoiceBusy(true);
    const label = action === 'start' ? `Start ${definition.name}` : 'Hold left';
    let target = `${definition.id}: ${label}`;
    setVoiceResult({ status: 'pending', target, message: 'Reading registered voice controls…' });
    try {
      const frame = getVoiceFrame();
      if (!frame) throw new Error('No published voice frame is registered.');
      const surface = await frame.read();
      const matches = surface.controls.filter(control => control.role === 'button' && control.label === label &&
        [definition.name, definition.id].some(name => control.context?.toLowerCase().includes(name.toLowerCase())));
      if (matches.length !== 1) throw new Error(`Expected one ${label} control in ${definition.name}; found ${matches.length}.`);
      const control = matches[0];
      target = `${definition.id}: ${control.label} [${control.id}] (${control.context})`;
      const result = await frame.execute({ type: 'click', id: control.id }, surface.version);
      setVoiceResult({ status: result.ok ? 'success' : 'error', target, message: result.message });
    } catch (error) {
      setVoiceResult({ status: 'error', target, message: error instanceof Error ? error.message : String(error) });
    } finally {
      voiceInFlight.current = false;
      setVoiceBusy(false);
    }
  };

  return <main style={{ fontFamily: 'system-ui,sans-serif', maxWidth: 1100, margin: '24px auto', padding: 20 }}>
    <style>{`.generated-frame{display:block;width:100%;border:0;margin-top:18px}button{padding:8px 12px;margin:3px}table{border-collapse:collapse;width:100%;font-size:13px;margin:16px 0}th,td{text-align:left;padding:8px;border-bottom:1px solid #ddd}code{font-size:12px}`}</style>
    <h1>Game runtime browser verification</h1>
    <p>This isolated fixture uses the real iframe bridge, Web Workers and QuickJS WASM. It never loads or changes saved spaces.</p>
    <p>Each game has its own ID, starting progress and checkpoint record. Start a tile, then use its direction buttons, hold an arrow key, or press and release a hold button. Only the focused game should receive input.</p>
    <p id="fixture-state">Mode: {multiple ? 'four games' : 'legacy single game'}. Revision: {revision}. Active games: {activeGames.length}. Checkpoints: {checkpointCount}. Draft: {String(pending)}. Mounted: {String(mounted)}.</p>
    <div aria-label="Fixture controls">
      <button onClick={() => setMultiple(value => !value)}>{multiple ? 'Use legacy single game' : 'Use four games'}</button>
      <button onClick={() => setMounted(value => !value)}>{mounted ? 'Remove frame' : 'Restore frame'}</button>
      <button onClick={() => setRevision(value => value + 1)}>Change revision</button>
      <button onClick={() => setPending(value => !value)}>{pending ? 'Show published' : 'Show draft'}</button>
    </div>
    <div aria-label="Individual tile controls">
      {definitions.map(definition => <button key={definition.id} onClick={() => toggleGame(definition.id)} disabled={!multiple && definition.id !== 'movingdot'}>
        {removed.has(definition.id) ? 'Restore' : 'Remove'} {definition.name}
      </button>)}
    </div>
    <p id="fixture-isolation" role="status">{failure || 'No cross-game checkpoints.'}</p>
    <fieldset>
      <legend>Registered voice controls, without a model</legend>
      <p>These buttons read the published frame and select a control by its label and game context. Pointer activation keeps focus in the game so testing a voice command does not pause it.</p>
      {definitions.map(definition => <div key={definition.id}>
        <button disabled={voiceBusy} onPointerDown={event => event.preventDefault()} onClick={() => void voiceAction(definition, 'start')}>Voice start {definition.name}</button>
        <button disabled={voiceBusy} onPointerDown={event => event.preventDefault()} onClick={() => void voiceAction(definition, 'left')}>Voice tap left {definition.name}</button>
      </div>)}
      <p id="fixture-voice-state" role="status" data-status={voiceResult.status} data-target={voiceResult.target}>Status: {voiceResult.status}. Target: {voiceResult.target}. Result: {voiceResult.message}</p>
    </fieldset>
    <table aria-label="Saved game records">
      <thead><tr><th>Game</th><th>Loads</th><th>Checkpoints</th><th>Saved ticks</th><th>Position</th><th>Held</th><th>Press / release</th></tr></thead>
      <tbody>{definitions.map(definition => {
        const record = records[definition.id];
        return <tr key={definition.id} id={`record-${definition.id}`} data-game-record={definition.id}>
          <th scope="row">{definition.name} <code>{definition.id}</code></th>
          <td data-record-field="loads">{record.loads}</td>
          <td data-record-field="checkpoints">{record.checkpoints}</td>
          <td data-record-field="ticks">{String(record.game.ticks)}</td>
          <td data-record-field="x">{String(record.game.x)}</td>
          <td data-record-field="held">{String(record.game.held)}</td>
          <td data-record-field="inputs">{String(record.game.presses)} / {String(record.game.releases)}</td>
        </tr>;
      })}</tbody>
    </table>
    {mounted && <GeneratedFrame html={html} games={multiple ? activeGames : undefined} game={multiple ? undefined : activeGames[0]} revisionId={revision} renderVersion={revision} pending={pending} onAction={async () => ({ ok: false })} />}
  </main>;
}

createRoot(document.getElementById('root')!).render(<App />);
