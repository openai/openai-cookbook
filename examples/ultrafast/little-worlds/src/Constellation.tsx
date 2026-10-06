import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties, KeyboardEvent, PointerEvent } from 'react';
import { gsap } from 'gsap';
import { Hand, Maximize, Minus, Orbit, Pause, Play, Plus } from 'lucide-react';
import SpaceIcon from './SpaceIcon';
import type { SpaceIcon as SpaceIconData } from './types';
import type { FriendConnection } from './Community';
import { clamp, galaxyDrift, initialCamera, positionForPerson, projectConstellation, projectGalaxyPoint, unprojectGalaxyPoint } from './constellation-layout';
import type { ConstellationCamera, GalaxyPoint, GalaxyProjection } from './constellation-layout';
import { readAppStorage } from './storage';
import './galaxy.css';

export type ConstellationPerson = { id: string; name: string; role: string; color: string; icon?: SpaceIconData };
type Props = { people: ConstellationPerson[]; connections: FriendConnection[]; currentUserId: string; selectedId: string | null; onSelect: (id: string) => void };
type Point = { x: number; y: number };
type Gesture = { kind: 'node' | 'camera'; id?: string; start: Point; previous: Point; offset: Point; depth: number; moved: boolean };
type PointerSample = Pick<globalThis.PointerEvent, 'pointerId' | 'clientX' | 'clientY' | 'buttons' | 'pointerType' | 'shiftKey'>;
type NodeHandle = { element: HTMLDivElement; x: (value: number) => void; y: (value: number) => void };
const random = (n: number) => { const value = Math.sin(n * 127.1 + 311.7) * 43758.5453; return value - Math.floor(value); };
const fieldPalettes = {
  dark: { axis: 'rgba(146,79,247,.15)', line: 'rgba(245,245,245,.045)', accent: '146,79,247', neutral: '245,245,245' },
  light: { axis: 'rgba(121,64,207,.18)', line: 'rgba(73,85,105,.085)', accent: '121,64,207', neutral: '73,85,105' },
};
// A quiet coordinate field shares the same camera as the worlds and connections.
const stars = Array.from({ length: 289 }, (_, i) => ({
  x: (i % 17 - 8) * .2, y: (Math.floor(i / 17) - 8) * .2, z: 0,
  radius: i % 19 === 0 ? 1.4 : .8, alpha: .2 + random(i + 13) * .22,
}));
function readPositions(key: string) {
  const result = new Map<string, GalaxyPoint>();
  try {
    const entries: unknown = JSON.parse(readAppStorage(localStorage, key) || '[]');
    if (Array.isArray(entries)) for (const entry of entries.slice(0, 100)) {
      if (!Array.isArray(entry) || typeof entry[0] !== 'string') continue;
      const point = entry[1];
      if (point && ['x', 'y', 'z'].every(axis => typeof point[axis] === 'number' && Number.isFinite(point[axis]) && Math.abs(point[axis]) <= 8)) result.set(entry[0], { x: point.x, y: point.y, z: point.z });
    }
  } catch { /* A private browser can still explore without saved placements. */ }
  return result;
}

export default function Constellation({ people, connections, currentUserId, selectedId, onSelect }: Props) {
  const storageKey = `little-worlds.galaxy-layout.v1:${currentUserId}`;
  const [reduced, setReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [playing, setPlaying] = useState(true);
  const [mode, setMode] = useState<'rotate' | 'pan'>('rotate');
  const [dragging, setDragging] = useState<string | null>(null);
  const [zoomPercent, setZoomPercent] = useState(100);
  const helpId = useId();
  const scene = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const fieldPalette = useRef(fieldPalettes.dark);
  const nodes = useRef(new Map<string, NodeHandle>());
  const edgePaths = useRef(new Map<string, SVGGElement>());
  const positions = useRef(readPositions(storageKey));
  const camera = useRef<ConstellationCamera>({ ...initialCamera });
  const size = useRef({ width: 800, height: 600 });
  const clock = useRef(0);
  const dirty = useRef(true);
  const pointers = useRef(new Map<number, Point>());
  const gesture = useRef<Gesture | null>(null);
  const projected = useRef(new Map<string, GalaxyProjection>());
  const cameraTween = useRef<gsap.core.Tween | null>(null);
  const resetTweens = useRef<gsap.core.Tween[]>([]);
  const resetting = useRef(false);
  const renderFrame = useRef(() => {});
  const motion = useRef({ playing, reduced });
  motion.current = { playing, reduced };
  const stablePeople = useMemo(() => [...people].sort((a, b) => a.id.localeCompare(b.id)), [people]);
  const peopleKey = stablePeople.map(person => person.id).join('|');
  const selectedConnections = new Set(connections.filter(edge => edge.source === selectedId || edge.target === selectedId).flatMap(edge => [edge.source, edge.target]));

  function savePositions() { try { localStorage.setItem(storageKey, JSON.stringify([...positions.current])); } catch { /* Storage is optional. */ } }
  function stopTweens(syncControls = true) { cameraTween.current?.kill(); cameraTween.current = null; resetTweens.current.forEach(tween => tween.kill()); resetTweens.current = []; resetting.current = false; if (syncControls) setZoomPercent(Math.round(camera.current.zoom * 100)); }
  function localPoint(client: Point): Point { const rect = scene.current!.getBoundingClientRect(); return { x: client.x - rect.left, y: client.y - rect.top }; }
  function moveCamera(next: Partial<ConstellationCamera>, animate = false) {
    cameraTween.current?.kill();
    if (animate && !motion.current.reduced) cameraTween.current = gsap.to(camera.current, { ...next, duration: .48, ease: 'power3.out', onUpdate: () => { dirty.current = true; }, onComplete: () => { cameraTween.current = null; setZoomPercent(Math.round(camera.current.zoom * 100)); } });
    else Object.assign(camera.current, next);
    if (next.zoom !== undefined) setZoomPercent(Math.round(next.zoom * 100));
    dirty.current = true;
    if (!animate || motion.current.reduced) renderFrame.current();
  }
  function zoom(factor: number, anchor?: Point, animate = true) {
    const current = camera.current;
    const value = clamp(current.zoom * factor, .65, 2.5), ratio = value / current.zoom;
    const point = anchor || { x: size.current.width / 2, y: size.current.height / 2 - 12 };
    const ax = point.x - size.current.width / 2, ay = point.y - size.current.height / 2 + 12;
    moveCamera({ zoom: value, x: clamp(ax - (ax - current.x) * ratio, -size.current.width, size.current.width), y: clamp(ay - (ay - current.y) * ratio, -size.current.height, size.current.height) }, animate);
  }

  renderFrame.current = () => {
    const view = size.current;
    const points = projectConstellation(stablePeople, camera.current, clock.current, view, positions.current);
    projected.current = new Map(points.map(person => [person.id, person]));
    for (const person of points) {
      const handle = nodes.current.get(person.id); if (!handle) continue;
      handle.x(person.x); handle.y(person.y);
      handle.element.style.setProperty('--node-scale', String(person.scale));
      handle.element.style.zIndex = String(person.id === gesture.current?.id || person.id === selectedId ? 35 : Math.round(15 + person.depth * 5));
    }
    for (const edge of connections) {
      const from = projected.current.get(edge.source), to = projected.current.get(edge.target), group = edgePaths.current.get(edge.id);
      if (!from || !to || !group) continue;
      const bend = Math.min(32, Math.hypot(to.x - from.x, to.y - from.y) * .08);
      const d = `M${from.x} ${from.y} Q${(from.x + to.x) / 2} ${(from.y + to.y) / 2 - bend} ${to.x} ${to.y}`;
      group.querySelectorAll('path').forEach(path => path.setAttribute('d', d));
      const light = group.querySelector<SVGPathElement>('.constellation-edge-light');
      if (light) light.style.strokeDashoffset = String(-clock.current * 12);
    }
    const ctx = canvas.current?.getContext('2d'); if (!ctx) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, view.width, view.height);
    // Fine reference lines make rotation and depth legible without ambient haze.
    for (let axis = 0; axis < 2; axis++) {
      for (let line = -4; line <= 4; line++) {
        const offset = line * .4;
        const from = projectGalaxyPoint({ x: axis ? offset : -1.6, y: axis ? -1.6 : offset, z: 0 }, camera.current, view);
        const to = projectGalaxyPoint({ x: axis ? offset : 1.6, y: axis ? 1.6 : offset, z: 0 }, camera.current, view);
        ctx.beginPath(); ctx.moveTo(from.x, from.y); ctx.lineTo(to.x, to.y);
        ctx.strokeStyle = line === 0 ? fieldPalette.current.axis : fieldPalette.current.line;
        ctx.lineWidth = .6; ctx.stroke();
      }
    }
    for (let i = 0; i < stars.length; i++) {
      const star = stars[i], point = projectGalaxyPoint(star, camera.current, view);
      ctx.beginPath(); ctx.arc(point.x, point.y, star.radius * Math.sqrt(camera.current.zoom), 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${i % 19 === 0 ? fieldPalette.current.accent : fieldPalette.current.neutral},${star.alpha})`; ctx.fill();
    }
    dirty.current = false;
  };

  useLayoutEffect(() => {
    const root = document.documentElement;
    const refreshPalette = () => {
      fieldPalette.current = fieldPalettes[root.dataset.theme === 'light' ? 'light' : 'dark'];
      dirty.current = true;
      renderFrame.current();
    };
    refreshPalette();
    const observer = new MutationObserver(refreshPalette);
    observer.observe(root, { attributes: true, attributeFilter: ['data-theme'] });
    return () => observer.disconnect();
  }, []);
  useLayoutEffect(() => { dirty.current = true; renderFrame.current(); });
  useEffect(() => {
    positions.current = readPositions(storageKey); dirty.current = true;
  }, [storageKey]);
  useEffect(() => {
    const element = scene.current; if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      size.current = { width: entry.contentRect.width, height: entry.contentRect.height };
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      if (canvas.current) { canvas.current.width = Math.round(size.current.width * dpr); canvas.current.height = Math.round(size.current.height * dpr); }
      dirty.current = true; renderFrame.current();
    });
    observer.observe(element);
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const changed = () => { setReduced(query.matches); dirty.current = true; if (query.matches) stopTweens(); };
    query.addEventListener('change', changed);
    const tick = (_time: number, delta: number) => {
      if (document.hidden) return;
      if (motion.current.playing && !motion.current.reduced && !pointers.current.size && !resetting.current) { clock.current += Math.min(delta, 48) / 1000; dirty.current = true; }
      if (dirty.current) renderFrame.current();
    };
    gsap.ticker.add(tick);
    return () => { observer.disconnect(); query.removeEventListener('change', changed); gsap.ticker.remove(tick); stopTweens(false); pointers.current.clear(); };
  }, []);
  useEffect(() => {
    const mm = gsap.matchMedia();
    mm.add('(prefers-reduced-motion: no-preference)', () => {
      const people = scene.current?.querySelectorAll('.galaxy-person-content');
      if (people?.length) gsap.fromTo(people, { opacity: 0, scale: .65, y: 18 }, { opacity: 1, scale: 1, y: 0, duration: .95, stagger: .065, ease: 'power3.out', clearProps: 'transform,opacity' });
      if (canvas.current) gsap.fromTo(canvas.current, { opacity: 0 }, { opacity: 1, duration: 1.6, ease: 'power2.out', clearProps: 'opacity' });
    });
    return () => mm.revert();
  }, [peopleKey]);
  useEffect(() => {
    const element = scene.current; if (!element) return;
    const wheel = (event: WheelEvent) => { event.preventDefault(); if (gesture.current?.kind === 'node') return; zoom(Math.exp(-clamp(event.deltaY, -100, 100) * .0024), localPoint({ x: event.clientX, y: event.clientY })); };
    element.addEventListener('wheel', wheel, { passive: false });
    return () => element.removeEventListener('wheel', wheel);
  });
  useEffect(() => {
    // Keep release handling alive when a pointer leaves the scene or a webview
    // delivers the release to the window instead of the captured element.
    const release = (event: globalThis.PointerEvent) => {
      if (!pointers.current.has(event.pointerId)) return;
      if (event.type === 'pointerup') move(event, true);
      finish(event.pointerId, event.type === 'pointerup');
    };
    const outsideMove = (event: globalThis.PointerEvent) => {
      if (!scene.current?.contains(event.target as Node)) move(event);
    };
    const blur = () => { for (const id of [...pointers.current.keys()]) finish(id); };
    window.addEventListener('pointerup', release);
    window.addEventListener('pointercancel', release);
    window.addEventListener('pointermove', outsideMove);
    window.addEventListener('blur', blur);
    return () => {
      window.removeEventListener('pointerup', release);
      window.removeEventListener('pointercancel', release);
      window.removeEventListener('pointermove', outsideMove);
      window.removeEventListener('blur', blur);
    };
  });

  function start(event: PointerEvent<HTMLDivElement>) {
    if (event.button > 0) return;
    stopTweens();
    const point = { x: event.clientX, y: event.clientY };
    pointers.current.set(event.pointerId, point);
    const target = (event.target as HTMLElement).closest<HTMLButtonElement>('[data-person-id]');
    if (pointers.current.size > 1) {
      if (gesture.current?.kind === 'node' && gesture.current.moved) savePositions();
      gesture.current = { kind: 'camera', start: point, previous: point, offset: { x: 0, y: 0 }, depth: 0, moved: true };
      setDragging('camera');
    } else if (target?.dataset.personId) {
      const id = target.dataset.personId, node = projected.current.get(id); if (!node) return;
      const local = localPoint(point);
      gesture.current = { kind: 'node', id, start: point, previous: point, offset: { x: node.x - local.x, y: node.y - local.y }, depth: node.depth, moved: false };
      target.focus({ preventScroll: true });
    } else {
      gesture.current = { kind: 'camera', start: point, previous: point, offset: { x: 0, y: 0 }, depth: 0, moved: false };
      event.currentTarget.focus({ preventScroll: true });
    }
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function move(event: PointerSample, releasing = false) {
    const previous = pointers.current.get(event.pointerId), active = gesture.current;
    if (!previous || !active) return;
    if (!releasing && event.pointerType === 'mouse' && event.buttons === 0) {
      finish(event.pointerId);
      return;
    }
    const next = { x: event.clientX, y: event.clientY };
    if (pointers.current.size > 1) {
      const other = [...pointers.current].find(([id]) => id !== event.pointerId)?.[1];
      if (other) {
        const before = Math.hypot(previous.x - other.x, previous.y - other.y), after = Math.hypot(next.x - other.x, next.y - other.y);
        const midpoint = localPoint({ x: (previous.x + other.x) / 2, y: (previous.y + other.y) / 2 });
        if (before > 10) zoom(after / before, midpoint, false);
        moveCamera({ x: clamp(camera.current.x + (next.x - previous.x) / 2, -size.current.width, size.current.width), y: clamp(camera.current.y + (next.y - previous.y) / 2, -size.current.height, size.current.height) });
      }
    } else {
      if (!active.moved && Math.hypot(next.x - active.start.x, next.y - active.start.y) < 5) { pointers.current.set(event.pointerId, next); return; }
      active.moved = true; setDragging(active.kind === 'node' ? active.id! : 'camera');
      if (active.kind === 'node' && active.id) {
        const local = localPoint(next);
        const point = unprojectGalaxyPoint({ x: clamp(local.x + active.offset.x, 38, size.current.width - 38), y: clamp(local.y + active.offset.y, 78, size.current.height - 90) }, active.depth, camera.current, size.current);
        positions.current.set(active.id, point); dirty.current = true; renderFrame.current();
      } else if (mode === 'pan' || event.shiftKey) moveCamera({ x: clamp(camera.current.x + next.x - previous.x, -size.current.width, size.current.width), y: clamp(camera.current.y + next.y - previous.y, -size.current.height, size.current.height) });
      else moveCamera({ yaw: camera.current.yaw + (next.x - previous.x) * .005, pitch: clamp(camera.current.pitch + (next.y - previous.y) * .004, -.85, .85) });
    }
    pointers.current.set(event.pointerId, next); active.previous = next;
  }
  function end(event: PointerEvent<HTMLDivElement>) {
    if (event.type === 'lostpointercapture' && (event.target !== event.currentTarget || event.currentTarget.hasPointerCapture(event.pointerId))) return;
    if (!pointers.current.has(event.pointerId)) return;
    // Only pointerup contains a trustworthy final position. Capture-loss and
    // cancellation events can carry zero coordinates and are never an undo.
    if (event.type === 'pointerup') move(event, true);
    finish(event.pointerId, event.type === 'pointerup');
  }
  function finish(pointerId: number, select = false) {
    if (!pointers.current.delete(pointerId)) return;
    const active = gesture.current;
    if (active?.kind === 'node' && active.moved) savePositions();
    if (pointers.current.size) {
      const point = [...pointers.current.values()][0];
      gesture.current = { kind: 'camera', start: point, previous: point, offset: { x: 0, y: 0 }, depth: 0, moved: true };
    } else {
      gesture.current = null; setDragging(null);
      if (select && active?.kind === 'node' && active.id && !active.moved) onSelect(active.id);
    }
    dirty.current = true; renderFrame.current();
    if (scene.current?.hasPointerCapture(pointerId)) scene.current.releasePointerCapture(pointerId);
  }
  function reset() {
    stopTweens();
    camera.current.yaw %= Math.PI * 2;
    if (camera.current.yaw > Math.PI) camera.current.yaw -= Math.PI * 2;
    if (camera.current.yaw < -Math.PI) camera.current.yaw += Math.PI * 2;
    let remaining = positions.current.size;
    resetting.current = remaining > 0 && !motion.current.reduced;
    for (const [id, point] of positions.current) {
      if (motion.current.reduced) { positions.current.delete(id); continue; }
      const base = positionForPerson(id), drift = galaxyDrift(id, clock.current);
      resetTweens.current.push(gsap.to(point, { x: base.x + drift.x, y: base.y + drift.y, z: base.z + drift.z, duration: .7, ease: 'power3.inOut', onUpdate: () => { dirty.current = true; }, onComplete: () => { positions.current.delete(id); savePositions(); dirty.current = true; if (--remaining === 0) { resetting.current = false; resetTweens.current = []; } } }));
    }
    savePositions(); moveCamera({ ...initialCamera }, true);
  }
  function keys(event: KeyboardEvent<HTMLDivElement>) {
    const target = (event.target as HTMLElement).closest<HTMLButtonElement>('[data-person-id]');
    if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
      event.preventDefault(); stopTweens();
      const dx = event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : 0, dy = event.key === 'ArrowUp' ? -1 : event.key === 'ArrowDown' ? 1 : 0;
      const id = target?.dataset.personId, node = id ? projected.current.get(id) : undefined;
      if (id && node) {
        const step = event.shiftKey ? 30 : 12;
        positions.current.set(id, unprojectGalaxyPoint({ x: clamp(node.x + dx * step, 38, size.current.width - 38), y: clamp(node.y + dy * step, 78, size.current.height - 90) }, node.depth, camera.current, size.current));
        savePositions(); dirty.current = true; renderFrame.current();
      } else if (event.shiftKey || mode === 'pan') moveCamera({ x: clamp(camera.current.x + dx * 30, -size.current.width, size.current.width), y: clamp(camera.current.y + dy * 30, -size.current.height, size.current.height) }, true);
      else moveCamera({ yaw: camera.current.yaw + dx * .14, pitch: clamp(camera.current.pitch + dy * .12, -.85, .85) }, true);
    } else if (event.key === '+' || event.key === '=') { event.preventDefault(); zoom(1.15); }
    else if (event.key === '-') { event.preventDefault(); zoom(1 / 1.15); }
    else if (event.key === 'Home') { event.preventDefault(); reset(); }
  }

  return <div className="constellation-shell galaxy-shell">
    <p id={helpId} className="galaxy-accessible-help">Drag a person to move them. Drag empty space to rotate the galaxy. Shift drag to pan. Scroll or pinch to zoom. Focus a person and use arrow keys to move them; Enter opens their profile. Focus the galaxy and use arrow keys to rotate. Home resets the layout and view.</p>
    <div ref={scene} className={`constellation-scene galaxy-scene${dragging ? ' dragging' : ''} mode-${mode}`} role="group" aria-label="Interactive community galaxy" aria-describedby={helpId} tabIndex={0} onPointerDown={start} onPointerMove={event => move(event)} onPointerUp={end} onPointerCancel={end} onLostPointerCapture={end} onDragStart={event => event.preventDefault()} onKeyDown={keys}>
      <canvas className="galaxy-stardust" ref={canvas} aria-hidden="true"/>
      <div className="galaxy-vignette" aria-hidden="true"/>
      <svg className="constellation-lines galaxy-lines" width="100%" height="100%" aria-hidden="true">
        {connections.map(edge => <g key={edge.id} ref={element => { if (element) edgePaths.current.set(edge.id, element); else edgePaths.current.delete(edge.id); }} className={`constellation-edge${selectedId && (edge.source === selectedId || edge.target === selectedId) ? ' highlighted' : ''}`}><path/><path className="constellation-edge-light"/></g>)}
      </svg>
      {stablePeople.map(person => <div key={person.id} className="galaxy-node" ref={element => {
        if (!element) { nodes.current.delete(person.id); return; }
        const previous = nodes.current.get(person.id);
        if (previous?.element !== element) nodes.current.set(person.id, { element, x: gsap.quickSetter(element, 'x', 'px') as (value: number) => void, y: gsap.quickSetter(element, 'y', 'px') as (value: number) => void });
      }} style={{ '--node-color': person.color } as CSSProperties}>
        <button data-person-id={person.id} className={`constellation-person${selectedId === person.id ? ' selected' : ''}${dragging === person.id ? ' is-held' : ''}${selectedId && person.id !== selectedId && !selectedConnections.has(person.id) ? ' unrelated' : ''}`} onClick={event => { if (event.detail === 0) onSelect(person.id); }} aria-label={`Meet ${person.name}${person.id === currentUserId ? ', you' : ''}`} aria-describedby={helpId} aria-pressed={selectedId === person.id}>
          <span className="galaxy-person-content"><span className="constellation-node-orbit"/><span className="constellation-node-portrait"><SpaceIcon icon={person.icon} size={68}/>{person.id === currentUserId && <i/>}</span><span className="constellation-node-name">{person.name}<span>{person.id === currentUserId ? 'YOU' : person.role.split(' & ')[0]}</span></span></span>
        </button>
      </div>)}
    </div>
    <div className="constellation-bottomline"><span className="constellation-hint"><span>Move a person</span><i/><span>Drag the canvas to {mode}</span></span><div className="constellation-tools" aria-label="Galaxy view controls"><button onClick={() => setPlaying(!playing)} disabled={reduced} aria-label={playing && !reduced ? 'Pause galaxy motion' : 'Play galaxy motion'} title={playing && !reduced ? 'Pause galaxy motion' : 'Play galaxy motion'}>{playing && !reduced ? <Pause size={15}/> : <Play size={15}/>}</button><div role="group" aria-label="Drag mode"><button className={mode === 'rotate' ? 'selected' : ''} onClick={() => setMode('rotate')} aria-label="Rotate galaxy" title="Rotate galaxy" aria-pressed={mode === 'rotate'}><Orbit size={17}/></button><button className={mode === 'pan' ? 'selected' : ''} onClick={() => setMode('pan')} aria-label="Pan galaxy" title="Pan galaxy" aria-pressed={mode === 'pan'}><Hand size={16}/></button></div><div role="group" aria-label="Zoom controls"><button onClick={() => zoom(1 / 1.15)} disabled={zoomPercent <= 65} aria-label="Zoom out" title="Zoom out"><Minus size={17}/></button><span aria-live="off">{zoomPercent}%</span><button onClick={() => zoom(1.15)} disabled={zoomPercent >= 250} aria-label="Zoom in" title="Zoom in"><Plus size={17}/></button></div><button onClick={reset} aria-label="Reset galaxy layout and view" title="Reset galaxy"><Maximize size={16}/></button></div></div>
  </div>;
}
