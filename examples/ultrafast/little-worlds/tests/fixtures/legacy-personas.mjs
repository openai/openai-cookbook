// Legacy authored-page fixtures retained only for compatibility tests.
// Production initialization never imports these modules; all live pages begin
// empty and are created by ordinary generated builder turns.
// Neuroscience references:
// https://www.nimh.nih.gov/news/media/2023/get-to-know-your-brain
// https://www.ninds.nih.gov/health-information/disorders/dementias

function escape(value) {
  return String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
}
function action(value) { return escape(JSON.stringify(value)); }
function ownRecord(state, namespace, actor, fallback) {
  const record = state.extras[namespace]?.[actor.id];
  return record?.actorId === actor.id ? record : fallback;
}
function withRecord(state, namespace, actor, value) {
  return { ...state, extras: { ...state.extras, [namespace]: { ...(state.extras[namespace] || {}), [actor.id]: { ...value, actorId: actor.id } } } };
}

const commonCss = `
*{box-sizing:border-box}button,input{font:inherit}button{cursor:pointer}button:disabled{cursor:default}button:focus-visible,input:focus-visible{outline:2px solid currentColor;outline-offset:4px}button{touch-action:manipulation}h1,h2,h3,p{margin:0}svg{display:block;max-width:100%}.eyebrow{text-transform:uppercase;letter-spacing:.16em;font-size:10px;font-weight:600}.serif{font-family:Georgia,'Times New Roman',serif;font-weight:400}.muted{opacity:.66}.person-signature{display:flex;align-items:center;gap:10px;font-size:11px}.person-signature i{height:6px;width:6px;display:block;background:currentColor;border-radius:50%}.fineprint{font-size:10px;line-height:1.55;opacity:.58}.sr-only{position:absolute;clip:rect(0,0,0,0);width:1px;height:1px;overflow:hidden}.segment{display:flex;gap:3px;padding:3px;border:1px solid currentColor;border-radius:24px}.segment button{border:0;background:transparent;color:inherit;padding:8px 13px;border-radius:20px;font-size:11px}.segment button[aria-pressed=true]{background:var(--ink);color:var(--paper)}@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}}`;

const miraCss = `
.botany{--ink:#294c36;--paper:#f0f1e7;color:var(--ink);background:var(--paper);border-radius:20px;overflow:hidden;font-family:'Trebuchet MS',sans-serif}.botany-head{display:flex;align-items:center;justify-content:space-between;gap:15px;padding:25px 29px 0}.botany-head .segment{border-color:#c6cfbc}.botany-hero{position:relative;min-height:274px;padding:40px 30px 28px;isolation:isolate}.botany-hero h1{font-size:clamp(37px,7.8vw,62px);line-height:1.04;letter-spacing:-.065em;max-width:70%;position:relative;z-index:2}.botany-hero p{font-size:12px;line-height:1.65;max-width:53%;margin-top:19px;color:#6b7862;position:relative;z-index:2}.hero-plant{position:absolute;width:45%;height:300px;right:0;bottom:-5px;opacity:.85;z-index:1;transform-origin:50% 100%;animation:breeze 10s ease-in-out infinite alternate}.botany-summer{--paper:#f4efe0;--ink:#55552c}.botany-evening{--paper:#e2e7df;--ink:#2e4745}.botany-evening .hero-plant{opacity:.7}.botany-label{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:8px 30px 17px;padding-top:18px;border-top:1px solid #cdd4c1}.botany-label p{font-size:11px;opacity:.75}.specimens{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;padding:0 21px 25px}.specimen{min-width:0;position:relative}.specimen-art{height:166px;border-radius:80px 80px 8px 8px;position:relative;overflow:hidden;border:1px solid rgba(64,83,48,.12);transition:transform .3s}.specimen:hover .specimen-art{transform:translateY(-4px)}.specimen-art svg{width:100%;height:100%;transform-origin:50% 100%;animation:breeze 8s ease-in-out infinite alternate}.specimen:nth-child(2n) svg{animation-delay:-3s}.specimen:nth-child(3n) svg{animation-delay:-5s}.specimen-index{position:absolute;left:12px;bottom:9px;font-size:9px;opacity:.55}.specimen h2{font-size:21px;letter-spacing:-.04em;margin:13px 0 5px}.specimen p{font-size:10px;line-height:1.6;opacity:.7;min-height:32px}.plant-vote{display:flex;gap:7px;align-items:center;justify-content:space-between;border-top:1px solid #c8cfbd;margin-top:13px;padding-top:11px}.plant-vote button{color:inherit;border:0;border-radius:18px;background:#dfe5d6;padding:8px 10px;font-size:10px;white-space:nowrap}.plant-vote button:disabled{opacity:.45}.plant-vote .remove-vote{padding:5px 9px;background:transparent;font-size:17px}.vote-count{font-size:10px;white-space:nowrap}.botany-foot{display:flex;justify-content:space-between;gap:15px;padding:15px 28px;border-top:1px solid #d0d6c7;font-size:10px;color:#748067}.small-leaf{font-size:15px;color:#819467}.botany-note{padding:0 29px 21px;font-size:11px;line-height:1.7;color:#748067}@keyframes breeze{from{transform:rotate(-2deg)}to{transform:rotate(2deg)}}@media(max-width:480px){.botany-head{padding:20px 19px 0;flex-wrap:wrap}.botany-head .segment button{padding:6px 10px}.botany-hero{min-height:255px;padding:34px 22px 25px}.botany-hero h1{font-size:43px;max-width:76%}.botany-hero p{max-width:63%;font-size:11px}.hero-plant{right:-23px;width:51%;opacity:.68;height:250px}.specimens{gap:16px;grid-template-columns:1fr;padding:0 22px 24px}.specimen{display:grid;grid-template-columns:110px 1fr;column-gap:19px;align-content:center}.specimen-art{height:155px;grid-row:1/5}.specimen h2{font-size:24px;margin:14px 0 5px}.specimen p{min-height:0}.plant-vote{margin-top:10px;align-self:end}.botany-label{margin-left:22px;margin-right:22px;align-items:flex-start;flex-direction:column}.botany-foot{padding:14px 22px}.botany-note{padding:0 22px 20px}}`;

function botanicalArt(kind, hero = false) {
  const stem = '#547148';
  if (kind % 3 === 0) {
    const leaves = [0, 1, 2, 3, 4, 5].map(i => {
      const y = 174 - i * 23;
      const x = 98 + Math.sin(i * .6) * 10;
      const spread = 44 - i * 4;
      return `<path d="M${x} ${y} Q${x - spread - 8} ${y - 3} ${x - spread} ${y - 31} Q${x - 4} ${y - 30} ${x} ${y}" fill="${i % 2 ? '#82986a' : '#6b875c'}"/><path d="M${x} ${y - 9} Q${x + spread + 6} ${y - 13} ${x + spread} ${y - 38} Q${x + 7} ${y - 32} ${x} ${y - 9}" fill="${i % 2 ? '#91a278' : '#748c61'}"/><path d="M${x - spread + 6} ${y - 27} L${x} ${y} L${x + spread - 4} ${y - 33}" fill="none" stroke="#c4cfa9" stroke-width=".6"/>`;
    }).join('');
    return `<svg viewBox="0 0 200 230" role="img" aria-label="Hand-drawn fern frond"><path d="M94 233 Q103 150 104 32" fill="none" stroke="${stem}" stroke-width="2"/>${leaves}<path d="M104 40 Q87 20 105 7 Q120 22 104 40" fill="#8d9e70"/></svg>`;
  }
  if (kind % 3 === 1) {
    return `<svg viewBox="0 0 200 230" role="img" aria-label="Moonflower on a climbing stem"><circle cx="141" cy="48" r="27" fill="#f6f0d7" opacity=".6"/><path d="M88 233 Q116 180 86 128 Q72 93 115 65" fill="none" stroke="${stem}" stroke-width="2"/><path d="M97 195 Q39 170 54 132 Q93 137 97 195M94 165 Q151 140 151 104 Q111 109 94 165" fill="#7b926c"/><path d="M90 133 Q55 105 61 83 Q89 89 90 133" fill="#91a27b"/><path d="M111 75 Q72 52 94 39 Q103 10 121 35 Q149 21 145 51 Q171 68 142 80 Q128 112 111 75" fill="#f7f4dc" stroke="#c1c8a1" stroke-width="1.4"/><path d="M121 55 L96 44 M121 55 L122 35 M121 55 L144 50 M121 55 L141 80 M121 55 L112 76" stroke="#d8d5a7"/><circle cx="121" cy="55" r="5" fill="#c3b873"/></svg>`;
  }
  return `<svg viewBox="0 0 200 230" role="img" aria-label="Young seedlings growing from a seed"><ellipse cx="99" cy="208" rx="59" ry="8" fill="#57633f" opacity=".09"/><path d="M103 206 Q93 143 101 81 M100 154 Q79 136 68 124 M99 119 Q120 105 134 85" fill="none" stroke="${stem}" stroke-width="2"/><path d="M100 153 Q39 156 42 115 Q72 103 100 153" fill="#8b9e6f"/><path d="M98 122 Q153 130 160 72 Q126 64 98 122" fill="#6f8a58"/><path d="M102 88 Q65 77 76 46 Q107 45 102 88" fill="#a5b181"/><path d="M102 89 Q139 64 125 36 Q96 44 102 89" fill="#809769"/><path d="M50 123 L99 152 M150 83 L100 121 M81 52 L101 87 M120 45 L101 88" fill="none" stroke="#d0d8b1" stroke-width=".7"/><ellipse cx="103" cy="205" rx="10" ry="5" fill="#a78a62"/></svg>`;
}

function renderMira(state, actor) {
  const view = ownRecord(state, 'gardenView', actor, { season: 'spring' });
  const season = ['spring', 'summer', 'evening'].includes(view.season) ? view.season : 'spring';
  const used = state.contributions.filter(item => item.actorId === actor.id).reduce((sum, item) => sum + item.points, 0);
  const colors = season === 'evening' ? ['#d4decd', '#b8c7bd', '#d2d8bf'] : ['#e2e7d4', '#e7e5cf', '#e4e2ca'];
  const cards = state.projects.map((project, index) => {
    const votes = state.contributions.filter(item => item.projectId === project.id).reduce((sum, item) => sum + item.points, 0);
    const mine = state.contributions.filter(item => item.projectId === project.id && item.actorId === actor.id).reduce((sum, item) => sum + item.points, 0);
    return `<article class="specimen"><div class="specimen-art" style="background:${colors[index % 3]}">${botanicalArt(index)}<span class="specimen-index">SPECIMEN ${String(index + 1).padStart(2, '0')}</span></div><h2 class="serif">${escape(project.title)}</h2><p>${escape(project.description)}</p><div class="plant-vote"><span class="vote-count">${votes} ${votes === 1 ? 'vote' : 'votes'}</span><div>${mine ? `<button class="remove-vote" aria-label="Remove your vote from ${escape(project.title)}" data-action="${action({ type: 'unsupport', projectId: project.id })}">−</button>` : ''}<button ${used >= 3 ? 'disabled' : ''} data-action="${action({ type: 'support', projectId: project.id })}" aria-label="Give a vote to ${escape(project.title)}">+ Grow</button></div></div></article>`;
  }).join('');
  return `<style>${COMMON_CSS}${PERSONA_CSS}</style><section class="botany botany-${season}"><header class="botany-head"><span class="eyebrow">Mira's living herbarium</span><div class="segment" aria-label="Garden light">${['spring', 'summer', 'evening'].map(item => `<button aria-pressed="${season === item}" data-action="${action({ type: 'season', season: item })}">${item[0].toUpperCase() + item.slice(1)}</button>`).join('')}</div></header><div class="botany-hero"><h1 class="serif">A softer kind<br>of growth.</h1><p>Plants, little experiments, and the quiet joy of watching something take root.</p><div class="hero-plant" aria-hidden="true">${botanicalArt(season === 'summer' ? 1 : season === 'evening' ? 2 : 0, true)}</div></div><div class="botany-label"><span class="eyebrow">In the greenhouse</span><p>${Math.max(0, 3 - used)} of 3 votes left · Help an idea grow</p></div><div class="specimens">${cards}</div><footer class="botany-foot"><span class="person-signature"><i></i>Tended by Mira, with a little help from you.</span><span class="small-leaf" aria-hidden="true">❧</span></footer></section>`;
}

function reduceMira(state, input, actor) {
  if (input.type === 'season') {
    if (!['spring', 'summer', 'evening'].includes(input.season)) throw new Error('Choose spring, summer, or evening.');
    return withRecord(state, 'gardenView', actor, { season: input.season });
  }
  if (!['support', 'unsupport'].includes(input.type)) throw new Error('That garden action is not available.');
  if (!state.projects.some(project => project.id === input.projectId)) throw new Error('Choose a project in this greenhouse.');
  if (input.type === 'unsupport') {
    const mine = state.contributions.find(item => item.actorId === actor.id && item.projectId === input.projectId);
    if (!mine) throw new Error('You have not voted for that project yet.');
    return { ...state, contributions: state.contributions.flatMap(item => item.id !== mine.id ? [item] : item.points > 1 ? [{ ...item, points: item.points - 1 }] : []) };
  }
  const used = state.contributions.filter(item => item.actorId === actor.id).reduce((sum, item) => sum + item.points, 0);
  if (used >= 3) throw new Error('Your three votes are planted. Remove one to move it elsewhere.');
  let suffix = 1;
  while (state.contributions.some(item => item.id === `garden-${actor.id}-${suffix}`)) suffix++;
  return { ...state, contributions: [...state.contributions, { id: `garden-${actor.id}-${suffix}`, actorId: actor.id, projectId: input.projectId, points: 1 }] };
}

const jamesCss = `
.finance{--paper:#f4f1e8;--ink:#172d3a;background:var(--paper);color:var(--ink);border-radius:20px;overflow:hidden;font-family:'Trebuchet MS',sans-serif}.finance-hero{background:#182f3b;color:#f2eadb;padding:30px 32px 23px;position:relative;overflow:hidden}.finance-hero .eyebrow{color:#b8c3b7}.finance-hero h1{font-size:clamp(37px,8vw,63px);letter-spacing:-.065em;line-height:1.03;margin:29px 0 18px;position:relative;z-index:2}.finance-hero p{max-width:300px;font-size:12px;line-height:1.7;color:#bbc6c7;position:relative;z-index:2}.finance-orbit{position:absolute;width:270px;height:270px;right:-112px;top:40px;border:1px solid #647d80;border-radius:50%;opacity:.4}.finance-orbit:before,.finance-orbit:after{content:'';position:absolute;inset:28px;border:1px solid #a1a187;border-radius:50%}.finance-orbit:after{inset:58px}.finance-signature{display:flex;justify-content:space-between;margin-top:28px;font-size:10px;color:#a3b5b5}.finance-body{padding:25px 30px}.finance-heading{display:flex;align-items:center;justify-content:space-between;gap:20px}.finance-heading h2{font-size:27px;letter-spacing:-.04em}.finance-heading span{font-size:9px;padding:6px 10px;border:1px solid #c7cabd;border-radius:16px;text-transform:uppercase;letter-spacing:.08em;white-space:nowrap}.growth-number{font-size:48px;letter-spacing:-.055em;line-height:1.1;margin-top:20px;font-variant-numeric:tabular-nums}.growth-caption{font-size:11px;color:#6e7b7b;margin-top:5px}.growth-chart{margin:18px 0 9px}.growth-chart svg{width:100%;height:160px;overflow:visible}.growth-line{stroke-dasharray:1000;stroke-dashoffset:1000;animation:draw-growth 1.5s ease forwards}.growth-key{display:flex;gap:18px;font-size:10px;color:#697a7b;margin-bottom:23px}.growth-key span{display:flex;gap:6px;align-items:center}.growth-key i{width:15px;height:2px;background:#a66c43}.growth-key span:last-child i{background:#a5b0a9}.finance-form{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.finance-form label{font-size:10px;color:#596b70;display:grid;gap:7px}.finance-form input{min-width:0;width:100%;border:1px solid #d3d5c9;border-radius:8px;background:#f9f7ef;padding:10px;color:#243c47;font-size:13px}.finance-form button{grid-column:1/-1;justify-self:start;border:0;border-radius:20px;padding:10px 17px;margin:4px 0 14px;background:#1d3944;color:#f7f4e8;font-size:11px}.finance .fineprint{margin-top:4px}.finance-foot{padding:18px 30px;border-top:1px solid #d5d8cb;display:flex;justify-content:space-between;gap:14px;font-size:10px;color:#62777a}@keyframes draw-growth{to{stroke-dashoffset:0}}@media(max-width:480px){.finance-hero{padding:25px 22px}.finance-hero h1{font-size:45px}.finance-hero p{max-width:75%}.finance-body{padding:24px 22px}.finance-form{grid-template-columns:repeat(2,minmax(0,1fr))}.finance-heading h2{font-size:24px}.finance-heading{gap:10px}.growth-number{font-size:clamp(28px,8vw,42px);overflow-wrap:anywhere}.finance-foot{padding:17px 22px;flex-wrap:wrap}}`;

function growthAt(principal, monthly, rate, months) {
  const r = rate / 1200;
  if (r === 0) return principal + monthly * months;
  return principal * Math.pow(1 + r, months) + monthly * (Math.pow(1 + r, months) - 1) / r;
}
function money(value) { return '$' + Math.round(value).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ','); }
function renderJames(state, actor) {
  const scenario = ownRecord(state, 'financeScenario', actor, { principal: 10000, monthly: 250, rate: 5, years: 20 });
  const valid = (value, min, max, fallback) => typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max ? value : fallback;
  const principal = valid(scenario.principal, 0, 500000, 10000);
  const monthly = valid(scenario.monthly, 0, 10000, 250);
  const rate = valid(scenario.rate, -10, 20, 5);
  const years = Number.isInteger(scenario.years) ? valid(scenario.years, 1, 40, 20) : 20;
  const months = years * 12;
  const total = growthAt(principal, monthly, rate, months);
  const deposits = principal + monthly * months;
  const max = Math.max(1, total, deposits) * 1.08;
  const y = value => (142 - value / max * 125).toFixed(2);
  const chart = Array.from({ length: 25 }, (_, i) => `${i === 0 ? 'M' : 'L'}${(12 + i / 24 * 470).toFixed(2)} ${y(growthAt(principal, monthly, rate, months * i / 24))}`).join(' ');
  const base = `M12 ${y(principal)} L482 ${y(deposits)}`;
  return `<style>${COMMON_CSS}${PERSONA_CSS}</style><section class="finance"><header class="finance-hero"><span class="eyebrow">James · Notes on the long view</span><div class="finance-orbit" aria-hidden="true"></div><h1 class="serif">Small decisions.<br>Long horizons.</h1><p>I work in finance. I'm fascinated by how patience, perspective, and a little curiosity compound.</p><div class="finance-signature"><span>Finance, made a little more human.</span><span aria-hidden="true">↗</span></div></header><div class="finance-body"><div class="finance-heading"><h2 class="serif">The compounding lab</h2><span>Try a scenario</span></div><p class="growth-number serif">${money(total)}</p><p class="growth-caption">Illustrative value after ${years} years · ${money(deposits)} contributed</p><div class="growth-chart"><svg viewBox="0 0 500 165" role="img" aria-label="Illustrative savings curve over ${years} years, ending at ${money(total)}"><defs><linearGradient id="growth-wash" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#bd976b" stop-opacity=".22"/><stop offset="1" stop-color="#bd976b" stop-opacity="0"/></linearGradient></defs><path d="M12 142 H482 M12 80 H482 M12 17 H482" fill="none" stroke="#d5d8cc" stroke-width=".7"/><path d="${chart} L482 142 L12 142Z" fill="url(#growth-wash)"/><path d="${base}" fill="none" stroke="#a5b0a9" stroke-width="1.5" stroke-dasharray="4 5"/><path class="growth-line" d="${chart}" fill="none" stroke="#a66c43" stroke-width="2.6" stroke-linecap="round"/><circle cx="482" cy="${y(total)}" r="4" fill="#a66c43"/><text x="12" y="162" fill="#7c8b89" font-size="9">Today</text><text x="482" y="162" text-anchor="end" fill="#7c8b89" font-size="9">Year ${years}</text></svg></div><div class="growth-key"><span><i></i>With compounding</span><span><i></i>Your contributions</span></div><form class="finance-form" data-action="${action({ type: 'scenario' })}"><label>Starting amount ($)<input name="principal" type="number" min="0" max="500000" step="100" required value="${principal}"></label><label>Per month ($)<input name="monthly" type="number" min="0" max="10000" step="10" required value="${monthly}"></label><label>Annual rate (%)<input name="rate" type="number" min="-10" max="20" step=".1" required value="${rate}"></label><label>Years<input name="years" type="number" min="1" max="40" step="1" required value="${years}"></label><button type="submit">Explore this scenario ↗</button></form><p class="fineprint">Illustration only, not a forecast or financial advice. Fixed annual rate, compounded monthly; deposits at month-end. Excludes taxes, fees, and inflation. Actual returns vary.</p></div><footer class="finance-foot"><span class="person-signature"><i></i>Curated by James</span><span>Good questions are a valuable asset.</span></footer></section>`;
}
function reduceJames(state, input, actor) {
  if (input.type !== 'scenario') throw new Error('Choose a scenario to explore.');
  const value = {};
  for (const [key, min, max] of [['principal', 0, 500000], ['monthly', 0, 10000], ['rate', -10, 20], ['years', 1, 40]]) {
    if (input[key] === undefined || input[key] === null || String(input[key]).trim() === '') throw new Error('Please fill in every scenario field.');
    const number = Number(input[key]);
    if (!Number.isFinite(number) || number < min || number > max || (key === 'years' && !Number.isInteger(number))) throw new Error(`Choose a valid ${key} between ${min} and ${max}.`);
    value[key] = number;
  }
  return withRecord(state, 'financeScenario', actor, value);
}

const jakeCss = `
.care{--ink:#244e50;--paper:#ecf3ef;background:var(--paper);color:var(--ink);border-radius:20px;overflow:hidden;font-family:'Trebuchet MS',sans-serif}.care-top{padding:25px 29px 0;display:flex;justify-content:space-between;align-items:center;gap:15px}.care-top .eyebrow{color:#678583}.care-top svg{width:21px;height:21px}.care-hero{padding:29px 29px 26px;position:relative;isolation:isolate}.care-hero h1{font-size:clamp(37px,7.4vw,55px);line-height:1.05;letter-spacing:-.06em;max-width:83%;position:relative;z-index:1}.care-hero p{font-size:12px;line-height:1.7;max-width:74%;margin-top:18px;color:#65837d;position:relative;z-index:1}.care-art{position:absolute;right:-10px;top:26px;width:170px;height:200px;opacity:.5;z-index:0}.care-note{padding:16px 29px;background:#e2eeea;display:flex;gap:13px;align-items:center;font-size:11px;line-height:1.65}.care-note svg{width:22px;height:22px;flex-shrink:0}.care-prep{padding:18px 29px 23px;border-top:1px solid #d2e1d8}.care-prep>button{border:0;background:transparent;padding:0;color:#456e68;text-align:left;font-size:11px;display:flex;justify-content:space-between;width:100%;align-items:center;gap:20px}.care-prep>button span{font-size:19px}.care-list{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-top:19px}.care-list h2{font-family:Georgia,serif;font-size:18px;font-weight:400;letter-spacing:-.025em;margin-bottom:6px}.care-list p{font-size:10px;line-height:1.7;color:#648179}.care-list i{font-size:9px;color:#81a298;display:block;margin-bottom:8px;font-style:normal}@media(max-width:480px){.care-top{padding:22px 21px 0}.care-hero{padding:28px 21px}.care-hero h1{font-size:43px;max-width:94%}.care-hero p{max-width:85%}.care-art{right:-54px;opacity:.3}.care-note{padding:16px 21px}.care-prep{padding:18px 21px 22px}.care-list{grid-template-columns:1fr;gap:13px}.care-list article{display:grid;grid-template-columns:20px 1fr;column-gap:8px}.care-list i{grid-row:1/3;margin-top:5px}.care-list p{grid-column:2}}`;
function renderJake(state, actor) {
  const open = ownRecord(state, 'careNotes', actor, { open: false }).open === true;
  return `<style>${COMMON_CSS}${PERSONA_CSS}.care-top{padding-top:18px}.care-hero{padding-top:17px;padding-bottom:18px}.care-hero h1{font-size:43px}.care-hero p{margin-top:12px;max-width:77%}.care-art{height:154px;top:8px;right:0}.care-prep{padding-top:12px;padding-bottom:12px}@media(max-width:480px){.care-hero h1{font-size:39px}.care-hero p{font-size:11px;max-width:85%}.care-art{right:-30px}}</style><section class="care"><header class="care-top"><span class="eyebrow">Jake · The care room</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v18M3 12h18" stroke="#6c9991" stroke-width="2" stroke-linecap="round"/></svg></header><div class="care-hero"><h1 class="serif">A little clarity.<br>A lot of care.</h1><p>I'm Jake, a nurse. A calm place to ask health questions and make the unfamiliar feel a little more familiar.</p><svg class="care-art" viewBox="0 0 180 220" aria-hidden="true"><path d="M86 213C83 170 135 153 144 105C154 57 117 11 85 16C51 21 61 70 83 95C109 124 71 148 36 133" fill="none" stroke="#9fc9bb" stroke-width="23" stroke-linecap="round"/><path d="M87 210C85 169 134 151 141 105C150 64 119 18 86 21C58 24 66 68 88 94C109 120 75 143 39 131" fill="none" stroke="#eff7ec" stroke-width="1"/><circle cx="36" cy="133" r="14" fill="#d4e7dc" stroke="#8cb8ad" stroke-width="2"/><circle cx="36" cy="133" r="7" fill="#eff7ec"/></svg></div><div class="care-prep"><button aria-expanded="${open}" data-action="${action({ type: 'toggleNotes' })}">A little preparation for your next appointment<span aria-hidden="true">${open ? '−' : '+'}</span></button>${open ? '<div class="care-list"><article><i>01</i><h2>What changed?</h2><p>Note what you noticed and when it began.</p></article><article><i>02</i><h2>What matters?</h2><p>Write down the questions you want to ask.</p></article><article><i>03</i><h2>What next?</h2><p>Ask your clinician to explain the next step in their plan.</p></article></div>' : ''}</div></section>`;
}
function reduceJake(state, input, actor) {
  if (input.type !== 'toggleNotes') throw new Error('That care-room action is not available.');
  const previous = ownRecord(state, 'careNotes', actor, { open: false });
  return withRecord(state, 'careNotes', actor, { open: previous.open !== true });
}

const ericaCss = `
.neuro{--ink:#423963;--paper:#eeeaf5;background:var(--paper);color:var(--ink);border-radius:20px;overflow:hidden;font-family:'Trebuchet MS',sans-serif}.neuro-top{padding:26px 29px 0;display:flex;justify-content:space-between;gap:10px;align-items:center}.neuro-top .eyebrow{color:#77678e}.neuro-top span:last-child{font-size:9px;color:#9586a9}.neuro-hero{padding:28px 29px 0;display:flex;gap:12px;align-items:flex-start}.neuro-hero h1{font-size:clamp(36px,7.1vw,53px);letter-spacing:-.06em;line-height:1.07;max-width:83%}.neuro-hero p{font-size:11px;line-height:1.7;color:#857393;max-width:190px;padding-top:8px}.brain-stage{position:relative;margin-top:9px;padding:0 22px}.brain-stage svg{height:228px;width:100%;overflow:visible}.brain-line{stroke-dasharray:5 8;animation:neural-signal 18s linear infinite}.brain-node{animation:neural-glow 4s ease-in-out infinite}.brain-note{position:absolute;font-size:9px;letter-spacing:.1em;text-transform:uppercase;bottom:8px;left:28px;color:#9989ae}.brain-controls{display:flex;justify-content:center;gap:7px;padding:14px 23px 20px}.brain-controls button{border:1px solid #cfc3df;border-radius:20px;background:transparent;color:#79658d;padding:9px 17px;font-size:11px}.brain-controls button[aria-pressed=true]{color:#f8f5ff;background:#64517f;border-color:#64517f}.brain-fact{margin:0 24px 24px;padding:21px 23px;background:#f8f6fb;border:1px solid #ded4e8;border-radius:12px;display:grid;grid-template-columns:44px 1fr;gap:12px}.brain-fact>span{font-family:Georgia,serif;font-size:33px;color:#ac98bf}.brain-fact h2{font-family:Georgia,serif;font-weight:400;font-size:24px;letter-spacing:-.035em}.brain-fact p{font-size:12px;line-height:1.7;margin:7px 0;color:#7a6b89}.brain-fact cite{font-style:normal;font-size:9px;color:#aa9cb7}.neuro-foot{border-top:1px solid #d8cfe4;padding:19px 29px 22px;display:grid;grid-template-columns:1fr 1fr;gap:18px}.neuro-foot .eyebrow{font-size:9px;margin-bottom:7px;color:#897799}.neuro-foot p{font-size:11px;line-height:1.7;color:#7c6c8c}.neuro-foot .fineprint{margin-top:7px;font-size:9px}@keyframes neural-signal{to{stroke-dashoffset:-140}}@keyframes neural-glow{0%,100%{opacity:.5}50%{opacity:1}}@media(max-width:480px){.neuro-top{padding:22px 21px 0;align-items:flex-start}.neuro-top span:last-child{max-width:60px;text-align:right}.neuro-hero{padding:28px 21px 0;display:block}.neuro-hero h1{font-size:43px;max-width:100%}.neuro-hero p{max-width:80%;padding-top:16px}.brain-stage{padding:0 6px}.brain-stage svg{height:207px}.brain-note{left:21px;font-size:8px}.brain-controls{padding:15px 15px 20px;gap:5px}.brain-controls button{padding:9px 14px}.brain-fact{margin:0 17px 20px;padding:18px 16px;grid-template-columns:30px 1fr;gap:8px}.brain-fact h2{font-size:23px}.brain-fact p{font-size:11px}.neuro-foot{padding:19px 22px;grid-template-columns:1fr;gap:14px}}`;
function brainArt(region) {
  const points = [[109, 103], [137, 65], [177, 45], [222, 42], [265, 54], [310, 81], [337, 113], [336, 145], [306, 177], [263, 185], [219, 176], [177, 182], [134, 160], [103, 135], [154, 114], [204, 91], [257, 109], [290, 139], [238, 146], [195, 135]];
  const active = region === 'attention' ? [0, 1, 2, 13, 14, 15] : region === 'memory' ? [14, 15, 18, 19, 10, 11] : [7, 8, 9, 16, 17, 18];
  const lines = points.map(([x, y], i) => [1, 4, 7].map(step => {
    const next = (i + step) % points.length;
    const [xx, yy] = points[next];
    const selected = active.includes(i) && active.includes(next);
    return `<path ${selected ? 'class="brain-line"' : ''} d="M${x} ${y}L${xx} ${yy}" stroke="${selected ? '#a57dc1' : '#c0acd0'}" opacity="${selected ? '.8' : '.24'}" stroke-width="${selected ? '1.4' : '.65'}" fill="none"/>`;
  }).join('')).join('');
  const nodes = points.map(([x, y], i) => `<circle class="${active.includes(i) ? 'brain-node' : ''}" cx="${x}" cy="${y}" r="${active.includes(i) ? '4.8' : '2.3'}" fill="${active.includes(i) ? '#9566b3' : '#bfa8cf'}" style="animation-delay:-${i % 4}s"/>`).join('');
  return `<svg viewBox="0 0 440 230" role="img" aria-label="Conceptual brain network with ${region} highlighted"><defs><radialGradient id="brain-aura"><stop stop-color="#c5a6e0" stop-opacity=".3"/><stop offset="1" stop-color="#eae2f2" stop-opacity="0"/></radialGradient></defs><ellipse cx="223" cy="119" rx="162" ry="108" fill="url(#brain-aura)"/><path d="M100 131C75 105 104 80 125 78C120 52 153 32 179 39C201 15 234 26 246 39C278 28 307 44 317 67C347 66 363 104 345 124C364 152 330 186 305 183C290 208 256 201 245 184C222 207 191 188 180 181C153 199 125 181 129 159C104 168 87 149 100 131Z" fill="none" stroke="#b79aca" stroke-width="1.2"/><path d="M236 175Q243 204 268 215M204 51Q183 65 200 88Q213 104 192 126Q178 147 195 171M262 56Q241 80 263 105Q283 122 269 145Q256 164 275 181M138 87Q158 72 179 85M112 129Q126 112 150 126M300 88Q321 102 305 123" fill="none" stroke="#c6b0d5" stroke-width="1"/>${lines}${nodes}</svg>`;
}
function renderErica(state, actor) {
  const selected = ownRecord(state, 'neuralExplorer', actor, { region: 'memory' }).region;
  const region = ['attention', 'memory', 'movement'].includes(selected) ? selected : 'memory';
  const facts = {
    attention: ['01', 'Making room to think', 'The frontal lobes help with complex thinking, learning, and problem-solving.', 'NIH / NIMH · Get to Know Your Brain'],
    memory: ['02', 'How moments become memories', 'The hippocampus is essential for forming memories. A small structure with a remarkable role in our everyday lives.', 'NIH / NINDS · Dementias'],
    movement: ['03', 'The quiet art of coordination', 'The cerebellum helps coordinate movement and balance, supporting the movements we learn and practice.', 'NIH / NIMH · Get to Know Your Brain'],
  };
  const [number, title, fact, citation] = facts[region];
  return `<style>${COMMON_CSS}${PERSONA_CSS}</style><section class="neuro"><header class="neuro-top"><span class="eyebrow">Erica · A mind in motion</span><span>Neuroscience field notes</span></header><div class="neuro-hero"><h1 class="serif">A universe,<br>under the surface.</h1><p>I study the connections that make us who we are. Come follow a little curiosity.</p></div><div class="brain-stage">${brainArt(region)}<span class="brain-note">A conceptual map · choose a connection</span></div><div class="brain-controls" aria-label="Explore a brain function">${['attention', 'memory', 'movement'].map(item => `<button aria-pressed="${item === region}" data-action="${action({ type: 'explore', region: item })}">${item[0].toUpperCase() + item.slice(1)}</button>`).join('')}</div><article class="brain-fact" aria-live="polite"><span>${number}</span><div><h2>${title}</h2><p>${fact}</p><cite>${citation}</cite></div></article><footer class="neuro-foot"><div><p class="eyebrow">What I'm curious about</p><p>Memory, neural plasticity, and the relationship between learning and connection.</p></div><div><p class="eyebrow">A note from Erica</p><p>The best part of research is finding a more interesting question.</p><p class="fineprint">Fictional demo persona. Educational illustration, not an anatomical scan.</p></div></footer></section>`;
}
function reduceErica(state, input, actor) {
  if (input.type !== 'explore' || !['attention', 'memory', 'movement'].includes(input.region)) throw new Error('Choose attention, memory, or movement.');
  return withRecord(state, 'neuralExplorer', actor, { region: input.region });
}

function miraTests(api) {
  const actor = { id: 'botany-seed-check', name: 'Garden visitor' };
  const other = { id: 'botany-other-check', name: 'Another visitor' };
  const state = JSON.parse(JSON.stringify(api.initialState));
  state.contributions = state.contributions.filter(item => ![actor.id, other.id].includes(item.actorId));
  const original = JSON.stringify(state);
  const project = state.projects[0];
  if (!project) return [{ name: 'The greenhouse has a project to support', ok: false }];
  const one = api.reduce(state, { type: 'support', projectId: project.id }, actor);
  const two = api.reduce(one, { type: 'support', projectId: project.id }, actor);
  const three = api.reduce(two, { type: 'support', projectId: project.id }, actor);
  let blocked = false;
  try { api.reduce(three, { type: 'support', projectId: project.id }, actor); } catch { blocked = true; }
  const moved = api.reduce(three, { type: 'unsupport', projectId: project.id }, actor);
  const season = api.reduce(moved, { type: 'season', season: 'evening' }, other);
  const fourth = { ...state, projects: [...state.projects, { id: 'fourth-test', title: 'Fourth specimen', description: 'A growing collection.', color: '#567764' }] };
  return [
    { name: 'Every project is rendered, including a new fourth tile', ok: api.render(fourth, actor).includes('Fourth specimen') },
    { name: 'Each visitor can plant three votes', ok: three.contributions.filter(item => item.actorId === actor.id).reduce((sum, item) => sum + item.points, 0) === 3 && blocked },
    { name: 'A visitor can remove one of their own votes', ok: moved.contributions.filter(item => item.actorId === actor.id).reduce((sum, item) => sum + item.points, 0) === 2 },
    { name: 'Existing saved contributions are preserved', ok: state.contributions.every(item => JSON.stringify(three.contributions.find(next => next.id === item.id)) === JSON.stringify(item)) },
    { name: 'Garden light belongs to the viewer', ok: season.extras.gardenView[other.id].actorId === other.id && api.render(season, other).includes('botany-evening') },
    { name: 'Rendering and interactions do not mutate their input', ok: JSON.stringify(state) === original },
  ];
}
function jamesTests(api) {
  const actor = { id: 'finance-seed-check', name: 'Scenario visitor' };
  const input = { type: 'scenario', principal: '1000', monthly: '100', rate: '0', years: '2' };
  const next = api.reduce(api.initialState, input, actor);
  let invalid = false;
  try { api.reduce(next, { ...input, rate: 'NaN' }, actor); } catch { invalid = true; }
  let excessive = false;
  try { api.reduce(next, { ...input, years: '100000' }, actor); } catch { excessive = true; }
  let fractional = false;
  try { api.reduce(next, { ...input, years: '1.5' }, actor); } catch { fractional = true; }
  const negative = api.reduce(next, { ...input, rate: '-5' }, actor);
  return [
    { name: 'Zero-rate savings equal principal plus monthly contributions', ok: api.render(next, actor).includes('$3,400') },
    { name: 'Scenario assumptions belong to their viewer', ok: next.extras.financeScenario[actor.id].actorId === actor.id },
    { name: 'Nonfinite, excessive, and fractional-duration inputs are rejected', ok: invalid && excessive && fractional },
    { name: 'Negative illustrative rates render without invalid arithmetic', ok: !api.render(negative, actor).includes('NaN') },
    { name: 'The calculator identifies its limits', ok: api.render(next, actor).includes('not a forecast') },
  ];
}
function jakeTests(api) {
  const actor = { id: 'care-seed-check', name: 'Care visitor' };
  const before = ownRecord(api.initialState, 'careNotes', actor, { open: false }).open === true;
  const open = api.reduce(api.initialState, { type: 'toggleNotes' }, actor);
  const restored = api.reduce(open, { type: 'toggleNotes' }, actor);
  let blocked = false;
  try { api.reduce(open, { type: 'setDiagnosis' }, actor); } catch { blocked = true; }
  return [
    { name: 'Appointment notes can be opened and closed', ok: open.extras.careNotes[actor.id].open === !before && restored.extras.careNotes[actor.id].open === before },
    { name: 'Care preferences belong to their viewer', ok: open.extras.careNotes[actor.id].actorId === actor.id },
    { name: 'The introduction invites health questions', ok: api.render(open, actor).includes('ask health questions') },
    { name: 'Unknown medical actions are rejected', ok: blocked },
  ];
}
function ericaTests(api) {
  const actor = { id: 'neuro-seed-check', name: 'Curious visitor' };
  const next = api.reduce(api.initialState, { type: 'explore', region: 'movement' }, actor);
  const memory = api.reduce(next, { type: 'explore', region: 'memory' }, actor);
  let invalid = false;
  try { api.reduce(memory, { type: 'explore', region: '<script>' }, actor); } catch { invalid = true; }
  return [
    { name: 'Selecting movement reveals the cerebellum fact', ok: api.render(next, actor).includes('cerebellum') },
    { name: 'Selecting memory changes the explanation', ok: api.render(memory, actor).includes('hippocampus') },
    { name: 'Brain exploration belongs to its viewer', ok: memory.extras.neuralExplorer[actor.id].actorId === actor.id },
    { name: 'Unknown regions are rejected', ok: invalid },
    { name: 'The illustration cites sources and identifies the demo persona', ok: api.render(next, actor).includes('NIH / NIMH') && api.render(next, actor).includes('Fictional demo persona') },
  ];
}

const commonSource = [escape, action, ownRecord, withRecord].map(fn => fn.toString()).join('\n');
function moduleSource(meta, css, render, reduce, helpers = []) {
  return `export const meta = ${JSON.stringify(meta, null, 2)};\nconst COMMON_CSS = ${JSON.stringify(commonCss)};\nconst PERSONA_CSS = ${JSON.stringify(css)};\n${commonSource}\n${helpers.map(fn => fn.toString()).join('\n')}\n${render.toString().replace(`function ${render.name}`, 'export function render')}\n${reduce.toString().replace(`function ${reduce.name}`, 'export function reduce')}\n`;
}
function testSource(fn) {
  return `${ownRecord.toString()}\n${fn.toString().replace(`function ${fn.name}`, 'export function runTests')}\n`;
}

const projects = [
  { id: 'tidepool', title: 'Fern studies', description: 'A collection of patient, unfurling things.', color: '#6b875c' },
  { id: 'afterhours', title: 'Moon garden', description: 'A small garden for the night bloomers.', color: '#91a27b' },
  { id: 'smallhours', title: 'Seed library', description: 'Good things, saved for another season.', color: '#a5b181' },
];
const seeds = {
  mira: {
    kind: 'studio',
    state: { projects, contributions: [], extras: {} },
    source: moduleSource({ title: "Mira's living herbarium", subtitle: 'A softer kind of growth.', accent: '#547148', layout: 'canvas', budget: 3, projects }, miraCss, renderMira, reduceMira, [botanicalArt]),
    tests: testSource(miraTests),
  },
  james: {
    kind: 'blank', state: { projects: [], contributions: [], extras: {} },
    source: moduleSource({ title: 'The long view', subtitle: 'Small decisions. Long horizons.', accent: '#24434d', layout: 'canvas' }, jamesCss, renderJames, reduceJames, [growthAt, money]),
    tests: testSource(jamesTests),
  },
  jake: {
    kind: 'blank', state: { projects: [], contributions: [], extras: {} },
    source: moduleSource({ title: 'The care room', subtitle: 'A little clarity. A lot of care.', accent: '#568c80', layout: 'canvas' }, jakeCss, renderJake, reduceJake),
    tests: testSource(jakeTests),
  },
  erica: {
    kind: 'blank', state: { projects: [], contributions: [], extras: {} },
    source: moduleSource({ title: 'A mind in motion', subtitle: 'A universe, under the surface.', accent: '#8b69aa', layout: 'canvas' }, ericaCss, renderErica, reduceErica, [brainArt]),
    tests: testSource(ericaTests),
  },
};

export function seedForPersona(ownerId) {
  const seed = Object.hasOwn(seeds, ownerId) ? seeds[ownerId] : undefined;
  return seed ? { ...seed, state: JSON.parse(JSON.stringify(seed.state)), version: 'personas-v1' } : undefined;
}
