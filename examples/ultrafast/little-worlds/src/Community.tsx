import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties, KeyboardEvent, ReactNode } from 'react';
import { ArrowUpRight, Check, ChevronRight, LoaderCircle, RotateCw, UserPlus, Users, X } from 'lucide-react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';
import NavigationControls, { type NavigationActions } from './NavigationControls';
import SpaceIcon from './SpaceIcon';
import DevDayBrand, { WorldBrackets } from './DevDayBrand';
import Constellation, { type ConstellationPerson } from './Constellation';
import { api, ApiError } from './api';
import type { SpaceSummary } from './types';
import './community.css';
import './community-motion.css';

gsap.registerPlugin(useGSAP);

// Old bookmarked routes still lead into the real community.
export type CommunityPlace = 'map' | 'noor' | 'jules' | 'sol';
export type CommunitySpace = SpaceSummary & { profile?: { role?: string; tagline?: string; theme?: string } };
export type FriendConnection = { id: string; source: string; target: string };
type FriendRequest = { id: string; fromId: string; toId: string; status: string; createdAt: string };
type CommunityData = { spaces: CommunitySpace[]; connections: FriendConnection[]; requests: { incoming: FriendRequest[]; outgoing: FriendRequest[] } };
type CommunityProps = { onClose: () => void; spaces?: CommunitySpace[]; currentUserId?: string; onVisit?: (spaceId: string) => void; navigation?: NavigationActions; place?: CommunityPlace; onPlaceChange?: (place: CommunityPlace) => void; onExpired?: () => void; footerControl?: ReactNode };
const personalities: Record<string, { role: string; tagline: string; color: string }> = {
  mira: { role: 'Botany & small wonders', tagline: 'A little closer to the living world.', color: '#04b84c' },
  james: { role: 'Finance & perspective', tagline: 'Finding the signal. Sharing the bigger picture.', color: '#924ff7' },
  jake: { role: 'Nursing & everyday care', tagline: 'Good questions deserve a caring answer.', color: '#04b84c' },
  erica: { role: 'Neuroscience & curiosity', tagline: 'A place to wonder about the mind.', color: '#924ff7' },
  leo: { role: 'A world in the making', tagline: 'Every new world starts with a little curiosity.', color: '#f5f5f5' },
  iris: { role: 'Painting & shared color', tagline: 'One canvas. Everyone’s mark.', color: '#924ff7' },
  luca: { role: 'Languages & little adventures', tagline: 'A little Spanish, a new adventure.', color: '#04b84c' },
  karen: { role: 'Arcades & one more game', tagline: 'One more game. Four little adventures.', color: '#924ff7' },
  nora: { role: 'Community & conversations', tagline: 'A town square for little worlds.', color: '#f5f5f5' },
};
function profile(space: CommunitySpace) {
  const fallback = personalities[space.owner.id] ?? { role: 'A world in the making', tagline: 'A space to make their own.', color: '#04b84c' };
  return { ...fallback, role: space.profile?.role || fallback.role, tagline: space.profile?.tagline || fallback.tagline };
}
function linked(connections: FriendConnection[], a: string, b: string) { return connections.some(edge => edge.source === a && edge.target === b || edge.source === b && edge.target === a); }
function orderSpaces(spaces: CommunitySpace[]) {
  const demoOrder = ['mira', 'james', 'jake', 'erica', 'leo', 'iris', 'luca', 'karen', 'nora'];
  const rank = (id: string) => { const index = demoOrder.indexOf(id); return index < 0 ? demoOrder.length : index; };
  return [...spaces].sort((a, b) => rank(a.owner.id) - rank(b.owner.id) || a.owner.name.localeCompare(b.owner.name));
}
function orderedData(data: CommunityData): CommunityData { return { ...data, spaces: orderSpaces(data.spaces) }; }

export default function Community({ onClose, spaces = [], currentUserId = '', onVisit, navigation, onExpired, footerControl }: CommunityProps) {
  const [data, setData] = useState<CommunityData>({ spaces: orderSpaces(spaces), connections: [], requests: { incoming: [], outgoing: [] } });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [requestsOpen, setRequestsOpen] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [announcement, setAnnouncement] = useState('');
  const [loaded, setLoaded] = useState(false);
  const overlay = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const profileCard = useRef<HTMLElement>(null);
  const requestsPanel = useRef<HTMLElement>(null);
  const requestsToggle = useRef<HTMLButtonElement>(null);
  const onExpiredRef = useRef(onExpired);
  const active = useRef(true);
  const requestVersion = useRef(0);
  const mutationPending = useRef(false);
  const previousConnectionIds = useRef<Set<string> | null>(null);

  // Each choreography owns its targets. matchMedia also reverts an in-flight
  // animation immediately when the viewer enables reduced motion.
  useGSAP(() => {
    const root = overlay.current;
    if (!root) return;
    const motion = gsap.matchMedia();
    motion.add('(prefers-reduced-motion: no-preference)', () => {
      const entrance = gsap.timeline({ defaults: { ease: 'power3.out' } });
      const enter = (selector: string, vars: gsap.TweenVars, at: number) => {
        const targets = root.querySelectorAll(selector);
        // The directory can still be empty while its first request is loading.
        if (targets.length) entrance.from(targets, vars, at);
      };
      enter('.community-header', { opacity: 0.5, y: -8, duration: 0.65 }, 0);
      enter('.community-intro .community-eyebrow', { opacity: 0, y: 9, duration: 0.7 }, 0.08);
      enter('.community-intro h1', { opacity: 0, y: 20, duration: 0.9 }, 0.12);
      enter('.community-intro p', { opacity: 0, y: 10, duration: 0.75 }, 0.22);
      enter('.community-section-label', { opacity: 0, y: 9, duration: 0.65 }, 0.2);
      enter('.community-person-row', { opacity: 0.35, x: 14, stagger: 0.045, duration: 0.6 }, 0.23);
    });
    return () => motion.revert();
  }, { scope: overlay });

  useGSAP(() => {
    const card = overlay.current?.querySelector(selectedId ? '.community-person-card' : '.community-discover-card');
    if (!card) return;
    const motion = gsap.matchMedia();
    motion.add('(prefers-reduced-motion: no-preference)', () => {
      const content = selectedId
        ? card.querySelectorAll('.community-person-identity, .community-person-tagline, .community-visit, .community-friend-action, .community-own-count')
        : card.querySelectorAll('.community-discover-mark, .community-eyebrow, h2, p');
      const entrance = gsap.timeline({ defaults: { ease: 'power3.out' } })
        .from(card, { opacity: 0.45, y: 11, scale: 0.985, duration: 0.48 }, 0);
      if (content.length) entrance.from(content, { opacity: 0.3, y: 7, duration: 0.45, stagger: 0.04 }, 0.03);
    });
    return () => motion.revert();
  }, { scope: overlay, dependencies: [selectedId], revertOnUpdate: true });

  useGSAP(() => {
    const panel = requestsPanel.current;
    if (!requestsOpen || !panel) return;
    const motion = gsap.matchMedia();
    motion.add('(prefers-reduced-motion: no-preference)', () => {
      const content = panel.querySelectorAll('.community-requests-heading, .community-requests-empty, .community-request-group');
      const entrance = gsap.timeline({ defaults: { ease: 'power3.out' } })
        .from(panel, { opacity: 0.35, y: -10, scale: 0.97, transformOrigin: '85% 0%', duration: 0.38 }, 0);
      if (content.length) entrance.from(content, { opacity: 0.5, y: 6, duration: 0.38, stagger: 0.045 }, 0.04);
    });
    return () => motion.revert();
  }, { scope: overlay, dependencies: [requestsOpen], revertOnUpdate: true });

  useGSAP(() => {
    const toast = overlay.current?.querySelector('.community-announcement');
    if (!announcement || !toast) return;
    const motion = gsap.matchMedia();
    motion.add('(prefers-reduced-motion: no-preference)', () => {
      const icon = toast.querySelector('svg');
      const entrance = gsap.timeline({ defaults: { ease: 'power3.out' } })
        .fromTo(toast, { opacity: 0, y: 12, scale: 0.96 }, { opacity: 1, y: 0, scale: 1, duration: 0.42 }, 0);
      if (icon) entrance.fromTo(icon, { scale: 0.5, rotation: -18 }, { scale: 1, rotation: 0, duration: 0.5, ease: 'back.out(1.7)' }, 0.08);
      entrance.to(toast, { opacity: 0, y: -5, duration: 0.3, ease: 'power2.in' }, 4.6);
    });
    return () => motion.revert();
  }, { scope: overlay, dependencies: [announcement], revertOnUpdate: true });

  useGSAP(() => {
    if (!loaded) return;
    const next = new Set(data.connections.map(connection => connection.id));
    const previous = previousConnectionIds.current;
    previousConnectionIds.current = next;
    if (!previous || ![...next].some(id => !previous.has(id))) return;
    const root = overlay.current;
    if (!root) return;
    const motion = gsap.matchMedia();
    motion.add('(prefers-reduced-motion: no-preference)', () => {
      const badges = root.querySelectorAll('.community-connected svg, .community-person-row strong svg');
      const count = root.querySelector('.community-intro > p > span');
      const connection = gsap.timeline();
      if (badges.length) connection.fromTo(badges, { scale: 0.6 }, { scale: 1, duration: 0.6, ease: 'back.out(2)', stagger: 0.04 }, 0);
      if (count) connection.fromTo(count, { color: '#f5f5f5' }, { color: '#04b84c', duration: 1.7, ease: 'power2.out' }, 0);
    });
    return () => motion.revert();
  }, { scope: overlay, dependencies: [data.connections, loaded], revertOnUpdate: true });

  onExpiredRef.current = onExpired;
  const refresh = useCallback(async () => {
    if (mutationPending.current) return;
    const version = ++requestVersion.current;
    try {
      const next = await api<CommunityData>('/api/community');
      if (!active.current || version !== requestVersion.current) return;
      setData(orderedData(next)); setLoaded(true); setError('');
    } catch (failure) {
      if (!active.current || version !== requestVersion.current) return;
      if (failure instanceof ApiError && failure.status === 401) onExpiredRef.current?.();
      setError('The neighborhood is reconnecting.');
    }
  }, []);
  useEffect(() => {
    active.current = true;
    void refresh();
    const timer = window.setInterval(() => { if (!document.hidden) void refresh(); }, 8000);
    const onVisible = () => { if (!document.hidden) void refresh(); };
    window.addEventListener('focus', onVisible); document.addEventListener('visibilitychange', onVisible);
    return () => { active.current = false; ++requestVersion.current; window.clearInterval(timer); window.removeEventListener('focus', onVisible); document.removeEventListener('visibilitychange', onVisible); };
  }, [refresh]);
  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden'; heading.current?.focus({ preventScroll: true });
    return () => { document.body.style.overflow = previousOverflow; previousFocus?.focus(); };
  }, []);
  useEffect(() => { if (!announcement) return; const timer = window.setTimeout(() => setAnnouncement(''), 5000); return () => window.clearTimeout(timer); }, [announcement]);
  useEffect(() => {
    if (selectedId && window.matchMedia('(max-width: 760px)').matches) {
      profileCard.current?.scrollIntoView({ block: 'nearest', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
    }
  }, [selectedId]);
  useEffect(() => { if (requestsOpen) requestsPanel.current?.querySelector<HTMLButtonElement>('button')?.focus(); }, [requestsOpen]);
  const selected = data.spaces.find(space => space.owner.id === selectedId);
  const selectedProfile = selected ? profile(selected) : null;
  const people = useMemo<ConstellationPerson[]>(() => data.spaces.map(space => ({ id: space.owner.id, name: space.owner.name, role: profile(space).role, color: profile(space).color, icon: space.icon })), [data.spaces]);
  const friendCount = data.connections.filter(edge => edge.source === currentUserId || edge.target === currentUserId).length;
  const incoming = selected ? data.requests.incoming.find(request => request.fromId === selected.owner.id) : undefined;
  const outgoing = selected ? data.requests.outgoing.find(request => request.toId === selected.owner.id) : undefined;
  const isFriend = !!selected && linked(data.connections, currentUserId, selected.owner.id);
  const isOwn = selected?.owner.id === currentUserId;
  async function act(key: string, path: string, body: unknown, message: string) {
    if (mutationPending.current) return;
    mutationPending.current = true; setPending(key); setError(''); ++requestVersion.current;
    try {
      const next = await api<CommunityData>(path, body);
      if (!active.current) return;
      ++requestVersion.current; setData(orderedData(next)); setLoaded(true); setAnnouncement(message);
    } catch (failure) {
      if (!active.current) return;
      if (failure instanceof ApiError && failure.status === 401) onExpiredRef.current?.();
      setError(failure instanceof Error ? failure.message : 'That connection could not be updated. Try again.');
    } finally { mutationPending.current = false; if (active.current) setPending(null); }
  }
  function respond(request: FriendRequest, decision: 'accept' | 'decline' | 'cancel') {
    const message = decision === 'accept' ? 'A new connection in your galaxy.' : decision === 'decline' ? 'Request declined.' : 'Request cancelled.';
    void act(request.id, '/api/friends/respond', { requestId: request.id, decision }, message);
  }
  function select(id: string) { setSelectedId(id); setRequestsOpen(false); }
  function closeRequests() { setRequestsOpen(false); requestsToggle.current?.focus(); }
  function visit(space: CommunitySpace) { if (onVisit) onVisit(space.id); else onClose(); }
  function handleKeys(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') { event.stopPropagation(); if (requestsOpen) closeRequests(); else if (selectedId) setSelectedId(null); else onClose(); }
    if (event.key !== 'Tab') return;
    const container = requestsOpen ? requestsPanel.current : overlay.current;
    const focusable = 'button:not(:disabled),a[href],input:not(:disabled),[tabindex="0"]';
    const voiceControls = requestsOpen ? overlay.current?.querySelector('.voice-dock')?.querySelectorAll<HTMLElement>(focusable) : [];
    const elements = [...new Set([...container?.querySelectorAll<HTMLElement>(focusable) || [], ...voiceControls || []])].filter(element => element.offsetParent !== null);
    if (requestsOpen && elements.length) {
      // The live controls remain reachable while this panel contains focus.
      // Cycle explicitly because unrelated overlay controls may sit between
      // the requests panel and the persistent voice dock in document order.
      const index = elements.indexOf(document.activeElement as HTMLElement);
      event.preventDefault();
      elements[index < 0 ? event.shiftKey ? elements.length - 1 : 0 : (index + (event.shiftKey ? -1 : 1) + elements.length) % elements.length].focus();
      return;
    }
    const first = elements[0]; const last = elements[elements.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === heading.current)) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  }
  return <div className="community-overlay" role="dialog" aria-modal="true" aria-labelledby="community-heading" ref={overlay} onKeyDown={handleKeys}>
    {footerControl}
    <header className="community-header"><div className="community-header-leading">
      <NavigationControls navigation={navigation ?? { goHome: () => window.location.assign('/') }}/>
      <DevDayBrand compact/><span className="community-place-name">Little Worlds / Community</span>
    </div><div className="community-header-actions"><button ref={requestsToggle} className={`community-requests-toggle${requestsOpen ? ' selected' : ''}`} onClick={() => setRequestsOpen(!requestsOpen)} aria-expanded={requestsOpen} aria-controls="community-requests" aria-label={`Friend requests${data.requests.incoming.length ? `, ${data.requests.incoming.length} incoming` : ''}`}><UserPlus size={16}/><span>Requests</span>{data.requests.incoming.length > 0 && <b>{data.requests.incoming.length}</b>}</button><button className="community-icon" onClick={onClose} aria-label="Close community and return to the space"><X size={19}/></button></div></header>
    <main className="community-main">
      <div className="community-intro"><div><span className="community-eyebrow">LITTLE WORLDS / OPENAI DEVDAY</span><h1 id="community-heading" ref={heading} tabIndex={-1}>Worlds built <em>together.</em></h1></div><p><span>{data.spaces.length} spaces <i/> {data.connections.length} connections</span></p></div>
      <div className="community-explore"><div className="community-universe"><Constellation people={people} connections={data.connections} currentUserId={currentUserId} selectedId={selectedId} onSelect={select}/>{!loaded && !data.spaces.length && <div className="community-loading"><LoaderCircle size={18}/>Finding your neighborhood…</div>}</div>
        <aside className="community-sidebar" aria-label="People and connections">
          {selected && selectedProfile ? <section ref={profileCard} className="community-person-card" key={selected.id} style={{ '--person-color': selectedProfile.color } as CSSProperties}>
            <div className="community-person-top"><span className="community-eyebrow">{isOwn ? 'YOUR LITTLE WORLD' : isFriend ? 'IN YOUR GALAXY' : 'A WORLD TO DISCOVER'}</span><button className="community-icon" onClick={() => setSelectedId(null)} aria-label="Close profile"><X size={15}/></button></div>
            <div className="community-person-identity"><SpaceIcon icon={selected.icon} size={65}/><div><h2>{selected.owner.name}</h2><span>{selectedProfile.role}</span></div></div><p className="community-person-tagline">{selectedProfile.tagline}</p>
            <button className="community-visit" onClick={() => visit(selected)}><span>Visit {isOwn ? 'your' : `${selected.owner.name}’s`} space</span><ArrowUpRight size={18}/></button>
            {!isOwn && <div className="community-friend-action">{isFriend ? <div className="community-outgoing-action"><span className="community-connected"><Check size={14}/>You’re connected</span><button className="community-subtle" disabled={!!pending} aria-label={`Remove ${selected.owner.name} as a friend`} onClick={() => void act(selected.owner.id, '/api/friends/remove', { targetId: selected.owner.id }, `${selected.owner.name} removed from your friends.`)}>{pending === selected.owner.id ? 'Removing…' : 'Remove friend'}</button></div> : incoming ? <div className="community-incoming-action"><span>Wants to connect with you</span><div><button className="community-connect" disabled={!!pending} onClick={() => respond(incoming, 'accept')}>{pending === incoming.id ? <LoaderCircle size={14}/> : <Check size={14}/>}Accept</button><button className="community-subtle" disabled={!!pending} onClick={() => respond(incoming, 'decline')}>Decline</button></div></div> : outgoing ? <div className="community-outgoing-action"><span><Check size={14}/>Request sent</span><button className="community-subtle" disabled={!!pending} onClick={() => respond(outgoing, 'cancel')}>Cancel</button></div> : <button className="community-connect" disabled={!!pending || !loaded} onClick={() => void act(selected.owner.id, '/api/friends/request', { targetId: selected.owner.id }, `Friend request sent to ${selected.owner.name}.`)}>{pending === selected.owner.id ? <LoaderCircle size={14}/> : <UserPlus size={14}/>}Add friend</button>}</div>}
            {isOwn && <span className="community-own-count"><Users size={14}/>{friendCount} {friendCount === 1 ? 'friend' : 'friends'} in your galaxy</span>}
          </section> : <div className="community-discover-card"><WorldBrackets className="community-discover-mark"/><span className="community-eyebrow">EXPLORE THE COMMUNITY</span><h2>A new <span className="community-discover-world">world.</span><br/>A new <span className="community-discover-connection">connection.</span></h2><p>Select a person to explore their world.</p></div>}
          <section className="community-people" aria-labelledby="community-people-heading"><div className="community-section-label"><h2 id="community-people-heading">People & worlds</h2><span>{people.length}</span></div><div className="community-people-list">{data.spaces.map(space => {
            const detail = profile(space); const connected = linked(data.connections, currentUserId, space.owner.id);
            return <button key={space.id} className={`community-person-row${selectedId === space.owner.id ? ' selected' : ''}`} onClick={() => select(space.owner.id)} aria-label={`Meet ${space.owner.name}${space.owner.id === currentUserId ? ', you' : connected ? ', your friend' : ''}`} aria-pressed={selectedId === space.owner.id}><SpaceIcon icon={space.icon} size={35}/><span><strong>{space.owner.name}{space.owner.id === currentUserId && <small>you</small>}{connected && <Check size={11} aria-label="Friend"/>}</strong><span>{detail.role}</span></span><ChevronRight size={14}/></button>;
          })}</div></section>
        </aside>
      </div>
    </main>
    {requestsOpen && <section ref={requestsPanel} className="community-requests" id="community-requests" aria-label="Friend requests"><div className="community-requests-heading"><div><span className="community-eyebrow">MAKE A CONNECTION</span><h2>Friend requests</h2></div><button className="community-icon" onClick={closeRequests} aria-label="Close friend requests"><X size={18}/></button></div>
      {!data.requests.incoming.length && !data.requests.outgoing.length && <div className="community-requests-empty"><UserPlus size={26} strokeWidth={1}/><p>No requests just yet.</p><span>Meet someone new and send a little hello.</span></div>}
      {!!data.requests.incoming.length && <div className="community-request-group"><h3>Waiting for you</h3>{data.requests.incoming.map(request => { const person = data.spaces.find(space => space.owner.id === request.fromId); return <div className="community-request-row" key={request.id}><SpaceIcon icon={person?.icon} size={38}/><div><button className="community-request-name" onClick={() => select(request.fromId)}>{person?.owner.name || 'A neighbor'}</button><span>wants to connect</span></div><button className="community-request-accept" disabled={!!pending} onClick={() => respond(request, 'accept')} aria-label={`Accept ${person?.owner.name || 'friend'} request`}>{pending === request.id ? <LoaderCircle size={15}/> : <Check size={15}/>}</button><button className="community-icon" disabled={!!pending} onClick={() => respond(request, 'decline')} aria-label={`Decline ${person?.owner.name || 'friend'} request`}><X size={15}/></button></div>; })}</div>}
      {!!data.requests.outgoing.length && <div className="community-request-group"><h3>Sent with curiosity</h3>{data.requests.outgoing.map(request => { const person = data.spaces.find(space => space.owner.id === request.toId); return <div className="community-request-row" key={request.id}><SpaceIcon icon={person?.icon} size={38}/><div><button className="community-request-name" onClick={() => select(request.toId)}>{person?.owner.name || 'A neighbor'}</button><span>request sent</span></div><button className="community-subtle" disabled={!!pending} onClick={() => respond(request, 'cancel')}>Cancel</button></div>; })}</div>}
    </section>}
    {error && <div className="community-error" role="alert"><span>{error}</span><button onClick={() => void refresh()} aria-label="Retry community connection"><RotateCw size={14}/></button></div>}
    <div className={`community-announcement${announcement ? ' visible' : ''}`} role="status" aria-live="polite">{announcement && <><Check size={14}/>{announcement}</>}</div>
  </div>;
}
