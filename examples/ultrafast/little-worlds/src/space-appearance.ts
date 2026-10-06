import type { SpaceAppearance } from './types';

/** Curated presentation only: the page's markup, state and running games stay intact. */
export function withSpaceAppearance(html: string, appearance?: SpaceAppearance): string {
  if (!appearance?.lightCss && !appearance?.presentationCss) return html;
  // Keep even an accidental closing tag inside the trusted stylesheet, rather
  // than allowing it to terminate the style element in an HTML document.
  const css = (appearance.lightCss || '').replace(/<\/style/gi, '<\\/style');
  const presentationCss = (appearance.presentationCss || '').replace(/<\/style/gi, '<\\/style');
  // The host's view transition fades the complete page once. Authored color
  // transitions must not start a second fade after that snapshot is captured.
  const motion = 'html body *,html body *::before,html body *::after{transition-property:transform,opacity,filter!important}';
  return `${html}<style data-space-appearance>${motion}${presentationCss}@media(prefers-color-scheme:light){${css}}</style>`;
}
