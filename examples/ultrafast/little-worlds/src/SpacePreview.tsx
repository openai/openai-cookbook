import { frameTheme } from './frame-theme';
import { memo, useEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import type { SpaceAppearance } from './types';
import { withSpaceAppearance } from './space-appearance';
import './space-preview.css';

type SpacePreviewProps = {
  html?: string;
  appearance?: SpaceAppearance;
  hasBuilt?: boolean;
  size?: number;
  name?: string;
  className?: string;
};

const VIEWPORT_SIZE = 720;
const VISIBLE_SIZE = 620;

function previewDocument(html: string) {
  // A template stays inert while we remove navigation and active content. The
  // separate, opaque-origin frame then enforces its own deny-by-default policy.
  const template = document.createElement('template');
  template.innerHTML = html;
  template.content.querySelectorAll('script, iframe, frame, frameset, object, embed, base, link, meta, animate, animateMotion, animateTransform, set, discard').forEach(element => element.remove());
  template.content.querySelectorAll('*').forEach(element => {
    for (const attribute of [...element.attributes]) {
      if (/^on/i.test(attribute.name) || ['autofocus', 'srcdoc', 'srcset', 'action', 'formaction', 'target'].includes(attribute.name.toLowerCase())) element.removeAttribute(attribute.name);
    }
  });
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; frame-src 'none'; object-src 'none'; media-src 'none'; form-action 'none'; base-uri 'none'"><style>${frameTheme}</style></head><body>${template.innerHTML}<style>*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important;caret-color:transparent!important}html,body{overflow:hidden!important}::-webkit-scrollbar{display:none}</style></body></html>`;
}

function SpacePreview({ html, appearance, hasBuilt, size = 68, name, className = '' }: SpacePreviewProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const [hasBeenVisible, setHasBeenVisible] = useState(false);
  const content = hasBuilt === false ? '' : html?.trim();
  const hasContent = Boolean(content);
  useEffect(() => {
    if (hasBeenVisible || !hasContent || !ref.current) return;
    if (typeof IntersectionObserver === 'undefined') {
      setHasBeenVisible(true);
      return;
    }
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) {
        setHasBeenVisible(true);
        observer.disconnect();
      }
    }, { rootMargin: '80px' });
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [hasBeenVisible, hasContent]);
  // Once revealed, retain the document as the galaxy moves or the list scrolls.
  const srcDoc = useMemo(() => hasBeenVisible && content ? previewDocument(withSpaceAppearance(content, appearance)) : undefined, [content, appearance?.lightCss, appearance?.presentationCss, hasBeenVisible]);
  const diameter = Number.isFinite(size) && size > 0 ? size : 68;
  const loading = (hasBuilt === true || hasContent) && !srcDoc;
  const style = {
    '--space-preview-size': `${diameter}px`,
    '--space-preview-scale': diameter / VISIBLE_SIZE,
    '--space-preview-offset': `${-28 * diameter / VISIBLE_SIZE}px`,
  } as CSSProperties;

  return <span
    ref={ref}
    className={`space-preview ${srcDoc ? 'space-preview-built' : 'space-preview-empty'}${loading ? ' space-preview-loading' : ''}${className ? ` ${className}` : ''}`}
    style={style}
    role={name ? 'img' : undefined}
    aria-label={name ? `${name}'s space${hasBuilt === false ? ', a blank canvas' : ''}` : undefined}
    aria-hidden={name ? undefined : true}
  >
    {srcDoc ? <iframe
      className="space-preview-frame"
      data-space-appearance={appearance?.lightCss ? '' : undefined}
      title="Space preview"
      srcDoc={srcDoc}
      sandbox=""
      inert
      tabIndex={-1}
      aria-hidden="true"
      referrerPolicy="no-referrer"
      loading="lazy"
      width={VIEWPORT_SIZE}
      height={VIEWPORT_SIZE}
    /> : <span className="space-preview-canvas" aria-hidden="true"><i /><i /><i /></span>}
  </span>;
}

export default memo(SpacePreview);
