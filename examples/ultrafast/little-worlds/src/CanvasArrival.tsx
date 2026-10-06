import { useRef } from 'react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';
import DevDayBrand, { WorldBrackets } from './DevDayBrand';
import './canvas-arrival.css';

gsap.registerPlugin(useGSAP);

/** A short approach to your world, over the already usable blank canvas. */
export default function CanvasArrival({ onComplete }: { onComplete?: () => void }) {
  const root = useRef<HTMLDivElement>(null);
  const completeCallback = useRef(onComplete);
  completeCallback.current = onComplete;

  useGSAP(() => {
    let alive = true;
    let completed = false;
    const complete = () => {
      if (!alive || completed) return;
      completed = true;
      gsap.set(root.current, { autoAlpha: 0 });
      completeCallback.current?.();
    };
    const media = gsap.matchMedia();
    media.add({ motion: '(prefers-reduced-motion: no-preference)', reduce: '(prefers-reduced-motion: reduce)' }, context => {
      if (context.conditions?.reduce) {
        complete();
        return;
      }
      if (completed) return;
      const select = gsap.utils.selector(root);
      gsap.set(root.current, { autoAlpha: 1 });

      // The event brackets open into the actual canvas. The overlay never
      // captures input and has no image-load or second-renderer dependency.
      gsap.timeline({ onComplete: complete })
        .fromTo(select('.canvas-arrival-world'),
          { scale: .92, opacity: 0 },
          { scale: 1, opacity: 1, duration: .35, ease: 'power2.out' }, 0)
        .fromTo(select('.canvas-arrival-signature'),
          { y: 6, opacity: 0 },
          { y: 0, opacity: 1, duration: .3, ease: 'power2.out' }, .12)
        .to(select('.world-bracket-left'), { x: -90, opacity: 0, duration: .45, ease: 'power2.inOut' }, .48)
        .to(select('.world-bracket-right'), { x: 90, opacity: 0, duration: .45, ease: 'power2.inOut' }, .48)
        .to(select('.world-brackets-center, .canvas-arrival-signature'), { opacity: 0, duration: .3 }, .57);

      // Also dismiss when a background tab pauses the animation ticker.
      const fallback = window.setTimeout(complete, 1400);
      return () => window.clearTimeout(fallback);
    }, root);
    return () => { alive = false; media.revert(); };
  }, { scope: root });

  return (
    <div ref={root} className="canvas-arrival" aria-hidden="true">
      <div className="canvas-arrival-art">
        <WorldBrackets className="canvas-arrival-world" />
        <div className="canvas-arrival-signature"><DevDayBrand compact/></div>
      </div>
    </div>
  );
}
