import { useEffect, useRef, useState } from 'react';
import gsap from 'gsap';
import './living-world.css';

/** Lazily loaded world. Drag physics never block the form or page navigation. */
export default function LivingWorld() {
  const host = useRef<HTMLDivElement>(null);
  const interaction = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const element = host.current!;
    const surface = interaction.current!;
    let cancelled = false;
    const cleanups: (() => void)[] = [];
    const dispose = () => {
      for (const cleanup of cleanups.splice(0).reverse()) {
        try { cleanup(); } catch { /* Keep releasing the remaining GPU resources. */ }
      }
    };

    async function mount() {
      const [THREE, { createLivingWorldScene }, { createGlobeRotation }] = await Promise.all([
        import('three'), import('./living-world-scene'), import('./globe-rotation'),
      ]);
      if (cancelled) return;

      const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'low-power' });
      cleanups.push(() => {
        renderer.dispose();
        renderer.forceContextLoss();
        renderer.domElement.remove();
      });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
      renderer.setClearColor(0x000000, 0);
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.08;
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFShadowMap;
      renderer.domElement.className = 'living-world-canvas';
      element.appendChild(renderer.domElement);

      const scene = new THREE.Scene();
      const camera = new THREE.OrthographicCamera(-1.65, 1.65, 1.65, -1.65, .1, 30);
      const { world, dispose: disposeWorld } = createLivingWorldScene();
      cleanups.push(disposeWorld);
      scene.add(world);
      scene.add(new THREE.HemisphereLight('#f5f5f5', '#25202e', 1.55));
      const sunlight = new THREE.DirectionalLight('#ffffff', 2.5);
      cleanups.push(() => sunlight.shadow.dispose());
      sunlight.position.set(-3, 6, 4);
      sunlight.castShadow = true;
      sunlight.shadow.mapSize.set(1024, 1024);
      sunlight.shadow.camera.left = -1.5;
      sunlight.shadow.camera.right = 1.5;
      sunlight.shadow.camera.top = 1.5;
      sunlight.shadow.camera.bottom = -1.5;
      sunlight.shadow.camera.near = .1;
      sunlight.shadow.camera.far = 15;
      sunlight.shadow.normalBias = .025;
      sunlight.shadow.bias = -.0001;
      sunlight.shadow.radius = 4;
      sunlight.shadow.intensity = .8;
      scene.add(sunlight);
      const fill = new THREE.DirectionalLight('#924ff7', .8);
      fill.position.set(3, 1, -2);
      scene.add(fill);

      const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
      let inViewport = true;
      let contextAvailable = true;
      let listening = false;
      let lastTime = 0;
      let activePointer: number | null = null;
      const rotation = createGlobeRotation();
      const pointer = { x: 0, y: 0 };
      const easedPointer = { x: 0, y: 0 };
      const center = new THREE.Vector3();

      function positionSurface() {
        // Match the actual projected sphere rather than grabbing the empty
        // corners of the illustration. Coordinates stay in CSS pixels.
        center.set(0, 0, 0).project(camera);
        const width = element.clientWidth, height = element.clientHeight;
        const radius = height / (camera.top - camera.bottom) * 1.03;
        surface.style.width = surface.style.height = `${radius * 2}px`;
        surface.style.left = `${(center.x + 1) * width / 2 - radius}px`;
        surface.style.top = `${(1 - center.y) * height / 2 - radius}px`;
      }

      function render() {
        if (!contextAvailable) return;
        camera.position.set(easedPointer.x * .22, .45 + easedPointer.y * .14, 5);
        camera.lookAt(0, .05, 0);
        world.quaternion.copy(rotation.quaternion);
        renderer.render(scene, camera);
        positionSurface();
      }

      const tick = (time: number) => {
        if (time - lastTime < 1 / (rotation.moving || rotation.dragging ? 60 : 30) - .001) return;
        const delta = Math.min(time - lastTime, .07);
        lastTime = time;
        rotation.step(delta, !motion.matches);
        const smoothing = 1 - Math.exp(-delta * 3);
        if (!rotation.dragging) {
          easedPointer.x += (pointer.x - easedPointer.x) * smoothing;
          easedPointer.y += (pointer.y - easedPointer.y) * smoothing;
        }
        render();
      };

      function syncMotion() {
        if (!contextAvailable || !inViewport || document.hidden) {
          finishGesture(false);
          if (rotation.moving) rotation.cancel();
        }
        if (motion.matches) {
          finishGesture(false);
          rotation.step(0, false);
          easedPointer.x = easedPointer.y = 0;
          render();
        }
        const animate = contextAvailable && inViewport && !document.hidden && !motion.matches;
        if (animate === listening) return;
        listening = animate;
        if (animate) {
          lastTime = gsap.ticker.time;
          gsap.ticker.add(tick);
        } else {
          gsap.ticker.remove(tick);
        }
      }
      cleanups.push(() => gsap.ticker.remove(tick));

      function resize() {
        finishGesture(false);
        const { width, height } = element.getBoundingClientRect();
        if (!width || !height) return;
        const aspect = width / height;
        camera.left = -1.35 * aspect;
        camera.right = 1.35 * aspect;
        camera.top = 1.35;
        camera.bottom = -1.35;
        camera.updateProjectionMatrix();
        renderer.setSize(width, height, false);
        render();
      }
      const observer = new ResizeObserver(resize);
      cleanups.push(() => observer.disconnect());
      observer.observe(element);
      const intersection = new IntersectionObserver(([entry]) => {
        inViewport = entry.isIntersecting;
        syncMotion();
      });
      cleanups.push(() => intersection.disconnect());
      intersection.observe(element);
      function move(event: PointerEvent) {
        if (event.pointerType === 'touch' || motion.matches || rotation.dragging) return;
        const bounds = element.getBoundingClientRect();
        pointer.x = Math.max(-1, Math.min(1, (event.clientX - bounds.left) / bounds.width * 2 - 1));
        pointer.y = Math.max(-1, Math.min(1, 1 - (event.clientY - bounds.top) / bounds.height * 2));
      }
      function leave() { pointer.x = pointer.y = 0; }
      function coordinates(event: PointerEvent) {
        const bounds = surface.getBoundingClientRect();
        return {
          x: (event.clientX - bounds.left - bounds.width / 2) / (bounds.width / 2),
          y: (bounds.top + bounds.height / 2 - event.clientY) / (bounds.height / 2),
        };
      }
      function grab(event: PointerEvent) {
        if (!contextAvailable || !event.isPrimary || event.button !== 0 || activePointer !== null) return;
        const point = coordinates(event);
        activePointer = event.pointerId;
        rotation.begin(point.x, point.y, event.timeStamp, camera.quaternion);
        surface.setPointerCapture(event.pointerId);
        surface.dataset.dragging = 'true';
        surface.dataset.pointerFocus = 'true';
        surface.focus({ preventScroll: true });
        event.preventDefault();
      }
      function drag(event: PointerEvent) {
        if (event.pointerId !== activePointer) return;
        const point = coordinates(event);
        rotation.drag(point.x, point.y, event.timeStamp);
        event.preventDefault();
        render();
      }
      function finishGesture(coast: boolean, time = performance.now()) {
        if (activePointer === null) return;
        const id = activePointer;
        activePointer = null;
        delete surface.dataset.dragging;
        if (coast && !motion.matches) rotation.end(time);
        else rotation.cancel();
        if (surface.hasPointerCapture(id)) surface.releasePointerCapture(id);
      }
      function release(event: PointerEvent) {
        if (event.pointerId !== activePointer) return;
        // Include the final segment when a browser coalesces the last move
        // into pointerup. A stationary release leaves the throw unchanged.
        const point = coordinates(event);
        rotation.drag(point.x, point.y, event.timeStamp);
        finishGesture(true, event.timeStamp);
      }
      function cancelGesture(event?: PointerEvent) {
        if (!event || event.pointerId === activePointer) finishGesture(false);
      }
      function lostCapture(event: PointerEvent) {
        // Embedded browsers can release capture before delivering pointerup,
        // or omit pointerup when the release lands outside the webview. End
        // with the last measured velocity; pointercancel handles real aborts.
        if (event.pointerId === activePointer) finishGesture(true, event.timeStamp);
      }
      function windowBlur() { finishGesture(false); if (rotation.moving) rotation.cancel(); }
      function clearPointerFocus() { delete surface.dataset.pointerFocus; }
      function keyboard(event: KeyboardEvent) {
        clearPointerFocus();
        const step = event.shiftKey ? .3 : .14;
        const keys: Record<string, [number, number]> = {
          ArrowLeft: [-step, 0], ArrowRight: [step, 0],
          ArrowUp: [0, step], ArrowDown: [0, -step],
        };
        if (event.key === 'Escape') { finishGesture(false); rotation.cancel(); return; }
        const turn = keys[event.key];
        if (!turn || !contextAvailable) return;
        event.preventDefault();
        finishGesture(false);
        rotation.nudge(...turn, camera.quaternion);
        render();
      }
      function contextLost(event: Event) {
        event.preventDefault();
        contextAvailable = false;
        syncMotion();
        setReady(false);
      }
      function contextRestored() {
        contextAvailable = true;
        resize();
        setReady(true);
        syncMotion();
      }
      const parent = element.closest('main') || element;
      parent.addEventListener('pointermove', move as EventListener);
      parent.addEventListener('pointerleave', leave);
      surface.addEventListener('pointerdown', grab);
      surface.addEventListener('pointermove', drag);
      surface.addEventListener('pointerup', release);
      surface.addEventListener('pointercancel', cancelGesture);
      surface.addEventListener('lostpointercapture', lostCapture);
      surface.addEventListener('keydown', keyboard);
      surface.addEventListener('blur', clearPointerFocus);
      window.addEventListener('blur', windowBlur);
      document.addEventListener('visibilitychange', syncMotion);
      motion.addEventListener('change', syncMotion);
      renderer.domElement.addEventListener('webglcontextlost', contextLost);
      renderer.domElement.addEventListener('webglcontextrestored', contextRestored);
      cleanups.push(() => {
        finishGesture(false);
        clearPointerFocus();
        parent.removeEventListener('pointermove', move as EventListener);
        parent.removeEventListener('pointerleave', leave);
        surface.removeEventListener('pointerdown', grab);
        surface.removeEventListener('pointermove', drag);
        surface.removeEventListener('pointerup', release);
        surface.removeEventListener('pointercancel', cancelGesture);
        surface.removeEventListener('lostpointercapture', lostCapture);
        surface.removeEventListener('keydown', keyboard);
        surface.removeEventListener('blur', clearPointerFocus);
        window.removeEventListener('blur', windowBlur);
        document.removeEventListener('visibilitychange', syncMotion);
        motion.removeEventListener('change', syncMotion);
        renderer.domElement.removeEventListener('webglcontextlost', contextLost);
        renderer.domElement.removeEventListener('webglcontextrestored', contextRestored);
      });
      resize();
      syncMotion();
      setReady(true);
    }

    // Keep the reserved space empty until the actual scene has rendered.
    mount().catch(() => { dispose(); if (!cancelled) setReady(false); });
    return () => { cancelled = true; dispose(); };
  }, []);

  return (
    <div className={`account-worlds living-world${ready ? ' is-ready' : ''}`}>
      <div className="living-world-shadow" />
      <div className="living-world-renderer" ref={host} aria-hidden="true" />
      <div
        className="living-world-interaction" ref={interaction} role="img"
        tabIndex={ready ? 0 : -1} aria-hidden={!ready || undefined}
        aria-label="Interactive globe. Drag to spin, or use the arrow keys to rotate."
      />
    </div>
  );
}
