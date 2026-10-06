import type { FrameVoiceViewport } from './voice-frame-registry';

type Box = { left: number; top: number; right: number; bottom: number; scaleX: number; scaleY: number };

// All coordinates here stay in the host viewport until the final conversion.
// Client dimensions exclude borders and scrollbar gutters, including a gutter
// on the left in RTL layouts. The app uses axis-aligned, uniform transforms.
function clientBox(element: HTMLElement): Box {
  const bounds = element.getBoundingClientRect();
  const scaleX = element.offsetWidth > 0 ? bounds.width / element.offsetWidth : 1;
  const scaleY = element.offsetHeight > 0 ? bounds.height / element.offsetHeight : 1;
  const left = bounds.left + element.clientLeft * scaleX;
  const top = bounds.top + element.clientTop * scaleY;
  return { left, top, right: left + element.clientWidth * scaleX,
    bottom: top + element.clientHeight * scaleY, scaleX, scaleY };
}

/** Visible slice of an opaque iframe in its own logical CSS coordinates. */
export function frameVoiceViewport(element: HTMLIFrameElement): FrameVoiceViewport {
  const view = element.ownerDocument.defaultView;
  if (!view) return { left: 0, top: 0, width: 0, height: 0 };
  const frame = clientBox(element);
  if (frame.scaleX <= 0 || frame.scaleY <= 0) return { left: 0, top: 0, width: 0, height: 0 };
  let left = Math.max(0, frame.left), top = Math.max(0, frame.top);
  let right = Math.min(view.innerWidth, frame.right), bottom = Math.min(view.innerHeight, frame.bottom);
  for (let parent = element.parentElement; parent; parent = parent.parentElement) {
    const style = view.getComputedStyle(parent);
    const clipsX = /^(auto|scroll|hidden|clip)$/.test(style.overflowX);
    const clipsY = /^(auto|scroll|hidden|clip)$/.test(style.overflowY);
    if (!clipsX && !clipsY) continue;
    const clip = clientBox(parent);
    if (clipsX) { left = Math.max(left, clip.left); right = Math.min(right, clip.right); }
    if (clipsY) { top = Math.max(top, clip.top); bottom = Math.min(bottom, clip.bottom); }
  }
  return {
    left: Math.min(element.clientWidth, Math.max(0, (left - frame.left) / frame.scaleX)),
    top: Math.min(element.clientHeight, Math.max(0, (top - frame.top) / frame.scaleY)),
    width: Math.max(0, right - left) / frame.scaleX,
    height: Math.max(0, bottom - top) / frame.scaleY,
  };
}
