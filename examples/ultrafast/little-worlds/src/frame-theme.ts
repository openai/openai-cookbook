
// System fonts keep opaque-origin frames independent of network font access. Authored CSS can specialize these defaults for the world's subject.
export const frameTheme = `
:root{color-scheme:dark;--devday-background:#000000;--devday-surface:#111111;--devday-text:#ffffff;--devday-muted:#a3a3a3;--devday-line:#2a2a2a;--devday-green:#04b84c;--devday-purple:#924ff7;--devday-blue:#006aff;--devday-orange:#ff8549}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--devday-background);color:var(--devday-text);font-family:system-ui,Arial,sans-serif;font-size:clamp(18px,1.5vw,32px);line-height:1.5}
body{display:flow-root;padding:2px 1px 4px}
button,input,textarea,select{font:inherit}
button{cursor:pointer;transition:background .15s,transform .15s}
button:focus-visible,a:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible{outline:3px solid var(--devday-green);outline-offset:3px}
button:active{transform:translateY(1px)}button:disabled{cursor:default}
a{color:inherit}svg{max-width:100%}[hidden]{display:none!important}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;transition:none!important;scroll-behavior:auto!important}}
`;
