import { withSpaceAppearance } from '../../src/space-appearance';
import sharedCss from '../../server/demo-presentation/shared.css?raw';
import natureCss from '../../server/demo-presentation/nature-finance.css?raw';
import lightCss from '../../server/demo-appearance/mira.css?raw';

// Relevant declarations from the prepared herbarium, preserving their order.
// The season rules originally came after the dark theme and replaced its ink.
const originalCascade = `
.herbarium.herbarium{--paper:#000000;--ink:#ffffff;--wash:#111111;--muted:#a0a0a0;--light:#57dc8c;background:#000000}
.herbarium.herbarium.summer{--light:#ff8549;--wash:#191919}
.herbarium.herbarium.evening{--light:#b58cff;--wash:#111111}
.herbarium.herbarium h1 em{color:var(--light);font-style:normal}
.herbarium.herbarium .lights button[aria-pressed=true]{background:#04b84c;color:#000000}
.herbarium{--paper:#f5f2e9;--ink:#294b35;--wash:#e6eadb;--muted:#67745e;background:var(--paper);color:var(--ink)}
.herbarium.summer{--paper:#f8f0d9;--wash:#eeead0;--ink:#48522c}
.herbarium.evening{--paper:#e4e8e0;--wash:#d4dfd3;--ink:#294b45;--muted:#5c7067}
.herbarium button{font:inherit;color:inherit;border:0}
.herbarium .lights{display:flex;padding:4px;background:var(--wash)}
.herbarium .lights button{background:transparent;padding:8px 12px}
.herbarium .intro,.herbarium .remaining{color:var(--muted)}
body{margin:0;font-family:Arial,sans-serif}
`;
const style = document.createElement('style');
style.textContent = `body{font:16px/1.5 Arial,sans-serif;margin:24px}#report{display:block;padding:16px;background:#eef3f0;white-space:pre-wrap}#cases{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}h2{font-size:18px}iframe{width:100%;height:360px;border:1px solid #777}@media(max-width:700px){#cases{grid-template-columns:1fr}}`;
document.head.append(style);

function luminance(color: string) {
  const rgb = color.match(/[\d.]+/g)?.slice(0, 3).map(Number);
  if (!rgb || rgb.length !== 3) throw new Error(`Unrecognized computed color ${color}`);
  const linear = rgb.map(channel => {
    const value = channel / 255;
    return value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4;
  });
  return linear[0] * .2126 + linear[1] * .7152 + linear[2] * .0722;
}
function contrast(foreground: string, background: string) {
  const a = luminance(foreground), b = luminance(background);
  return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
}
async function run() {
  const failures: string[] = [];
  const measurements: object[] = [];
  let checks = 0;
  for (const season of ['spring', 'summer', 'evening']) {
    for (const theme of ['dark', 'light']) {
      const section = document.createElement('section');
      const heading = document.createElement('h2');
      heading.textContent = `${season} / ${theme}`;
      const frame = document.createElement('iframe');
      frame.title = heading.textContent;
      frame.style.colorScheme = theme;
      section.append(heading, frame);
      document.querySelector('#cases')!.append(section);
      const loaded = new Promise<void>(resolve => frame.addEventListener('load', () => resolve(), { once: true }));
      const markup = `<style>${originalCascade}</style><main class="herbarium ${season}"><div class="lights">${['spring', 'summer', 'evening'].map(label => `<button aria-pressed="${season === label}">${label}</button>`).join('')}</div><h1>Small wonders. <em>Still unfolding.</em></h1><p class="intro">A collection of quiet discoveries.</p><p class="remaining">3 of 3 points left · Help an idea grow</p></main>`;
      frame.srcdoc = `<!doctype html><html><head><meta charset="UTF-8"></head><body>${withSpaceAppearance(markup, { lightCss, presentationCss: sharedCss + natureCss })}</body></html>`;
      await loaded;
      const doc = frame.contentDocument!;
      const view = frame.contentWindow!;
      await new Promise<void>(resolve => view.requestAnimationFrame(() => view.requestAnimationFrame(() => resolve())));
      const background = view.getComputedStyle(doc.querySelector('.herbarium')!).backgroundColor;
      for (const selector of ['h1', '.intro', '.remaining', '.lights button[aria-pressed="false"]', '.lights button[aria-pressed="true"]']) {
        const element = doc.querySelector(selector)!;
        const computed = view.getComputedStyle(element);
        const buttonBackground = computed.backgroundColor;
        const backing = selector.includes('button')
          ? (buttonBackground === 'rgba(0, 0, 0, 0)' ? view.getComputedStyle(doc.querySelector('.lights')!).backgroundColor : buttonBackground)
          : background;
        const ratio = contrast(computed.color, backing);
        checks++;
        measurements.push({ season, theme, selector, foreground: computed.color, background: backing, ratio });
        if (ratio < 4.5) failures.push(`${season}/${theme} ${selector}: ${ratio.toFixed(2)}:1 contrast`);
      }
      checks++;
      if (view.matchMedia('(prefers-color-scheme:light)').matches !== (theme === 'light')) failures.push(`${season}/${theme}: embedded theme mismatch`);
    }
  }
  const report = document.querySelector('#report')!;
  report.textContent = failures.length ? `FAIL: ${failures.join('\n')}` : `PASS: ${checks} checks across all six theme/season combinations`;
  report.setAttribute('data-result', failures.length ? 'fail' : 'pass');
  report.setAttribute('data-measurements', JSON.stringify(measurements));
}
void run().catch(error => {
  const report = document.querySelector('#report')!;
  report.textContent = `FAIL: ${error instanceof Error ? error.message : String(error)}`;
  report.setAttribute('data-result', 'fail');
});
