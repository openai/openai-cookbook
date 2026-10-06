import { useEffect, useId, useRef, useState } from 'react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';
import NavigationControls, { type NavigationActions } from './NavigationControls';
import SpaceIcon from './SpaceIcon';
import LivingWorld from './LivingWorld';
import DevDayBrand from './DevDayBrand';
import type { AccountPerson } from './types';
import './account.css';

gsap.registerPlugin(useGSAP);

type AccountGateProps = {
  people: AccountPerson[];
  busy: boolean;
  error: string | null;
  onChoose: (userId: string) => void;
  onCreate: (name: string) => void;
  navigation?: NavigationActions;
};

function Arrow() {
  return <svg viewBox="0 0 24 24" width="20" height="20" fill="none" aria-hidden="true"><path d="M5 12h14m-5-5 5 5-5 5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

export default function AccountGate({ people, busy, error, onChoose, onCreate, navigation }: AccountGateProps) {
  const [flow, setFlow] = useState<'create' | 'login'>('create');
  const [name, setName] = useState('');
  const [pending, setPending] = useState<string | null>(null);
  const screen = useRef<HTMLElement>(null);
  const flowHeading = useRef<HTMLHeadingElement>(null);
  const hasNavigated = useRef(false);
  const nameId = useId();
  const errorId = useId();
  const normalizedName = name.trim().replace(/\s+/g, ' ');
  function selectFlow(next: typeof flow) {
    hasNavigated.current = true;
    setFlow(next);
  }
  useEffect(() => {
    if (hasNavigated.current) flowHeading.current?.focus({ preventScroll: true });
  }, [flow]);

  useGSAP(() => {
    const media = gsap.matchMedia();
    media.add('(prefers-reduced-motion: no-preference)', () => {
      const root = screen.current!;
      const select = gsap.utils.selector(root);
      gsap.timeline({ defaults: { ease: 'power3.out' } })
        .from(select('.account-header'), { y: -8, opacity: 0, duration: .65 })
        .from(select('.account-introduction h1, .account-intro-copy'), { y: 14, opacity: 0, duration: .8, stagger: .08 }, .15)
        .from(select('.account-world-frame .account-corner'), { scale: .8, opacity: 0, duration: .9, stagger: .07 }, .3)
        .from(select('.account-footer'), { opacity: 0, duration: .7 }, .45);

    }, screen);
    return () => media.revert();
  }, { scope: screen });

  useGSAP(() => {
    const media = gsap.matchMedia();
    media.add('(prefers-reduced-motion: no-preference)', () => {
      gsap.from('.account-entry-heading, .account-new, .account-flow-back', { y: 12, opacity: 0, duration: .65, stagger: .055, ease: 'power3.out', clearProps: 'transform,opacity' });
      if (flow === 'login') gsap.from('.account-person', { opacity: 0, duration: .6, stagger: .055, ease: 'power2.out', clearProps: 'opacity' });
    }, screen);
    return () => media.revert();
  }, { scope: screen, dependencies: [flow], revertOnUpdate: true });

  return (
    <main ref={screen} className="account-gate">
      <header className="account-header">
        <div className="page-header-leading">
        {navigation && <NavigationControls navigation={{ goHome: () => { selectFlow('create'); navigation.goHome(); } }} />}
        <DevDayBrand />
        </div>
        {flow === 'create' && <button className="account-login-link" disabled={busy} onClick={() => selectFlow('login')}>Log in <Arrow /></button>}
      </header>

      <div className="account-layout">
        <section className="account-introduction" aria-labelledby="account-title">
          <h1 id="account-title"><span className="account-world-name">Little worlds.</span><br />Big possibilities.</h1>
          <p className="account-intro-copy"><span className="account-intro-accent">Imagine a place.</span> Bring it to life with AI.</p>
          <div className="account-world-frame">
            <span className="account-corner account-corner-top-left" aria-hidden="true" />
            <span className="account-corner account-corner-top-right" aria-hidden="true" />
            <LivingWorld />
            <span className="account-corner account-corner-bottom-left" aria-hidden="true" />
            <span className="account-corner account-corner-bottom-right" aria-hidden="true" />
          </div>
        </section>

        <section className={`account-entry account-flow-${flow}`} aria-labelledby="account-entry-title" aria-busy={busy} onKeyDown={event => {
          if (event.key === 'Escape' && flow === 'login' && !busy) { event.preventDefault(); selectFlow('create'); }
        }}>
          {flow === 'login' && <button className="account-flow-back" disabled={busy} onClick={() => selectFlow('create')} aria-label="Back to welcome"><Arrow /><span>Back</span></button>}
          <div className="account-entry-heading">
            <span className="account-entry-index" aria-hidden="true">{flow === 'create' ? '[01]' : '[02]'}</span>
            <h2 id="account-entry-title" ref={flowHeading} tabIndex={-1}>{flow === 'create' ? <>Make a <span className="account-world-name">little world.</span></> : 'Welcome back.'}</h2>
            <p>{flow === 'create' ? 'Enter your name to make a space of your own.' : 'Choose your space. Pick up where you left off.'}</p>
          </div>

          {flow === 'login' && people.length > 0 && <div className="account-people" aria-label="Saved people">
            {people.map(person => (
              <button className="account-person" key={person.id} disabled={busy} onClick={() => { setPending(person.id); onChoose(person.id); }} aria-label={`Continue as ${person.name}`}>
                <SpaceIcon icon={person.icon} size={44}/>
                <span className="account-person-copy"><strong>{person.name}</strong><span>{busy && pending === person.id ? 'Opening your space…' : 'Enter your space'}</span></span>
                <span className="account-person-arrow"><Arrow /></span>
              </button>
            ))}
          </div>}
          {flow === 'login' && people.length === 0 && !busy && <p className="account-empty">No saved spaces yet. <button onClick={() => selectFlow('create')}>Create the first one.</button></p>}

          {flow === 'create' && <form className="account-new account-create-form" onSubmit={event => { event.preventDefault(); if (!busy && normalizedName) { setPending('new'); onCreate(normalizedName); } }}>
            <div className="account-name-row">
              <input id={nameId} name="displayName" autoComplete="off" value={name} onChange={event => setName(event.target.value)} placeholder="Your name" aria-label="Your name" maxLength={40} disabled={busy} aria-describedby={error ? errorId : undefined} />
              <button type="submit" disabled={busy || !normalizedName} aria-label={busy && pending === 'new' ? 'Creating your space' : 'Create a space'}><Arrow /></button>
            </div>
          </form>}

          {error && <p id={errorId} className="account-error" role="alert">{error}</p>}
          <p className="account-loading" role="status" aria-live="polite">{busy && pending === 'new' ? 'Making room for you…' : '\u00a0'}</p>
        </section>
      </div>

      <footer className="account-footer"><span className="account-footer-title">Little Worlds</span><span className="account-footer-edition">DEVDAY [2026]</span></footer>
    </main>
  );
}
