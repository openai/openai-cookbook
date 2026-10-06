export const actors = {
  mira: { id: 'mira', name: 'Mira' },
  leo: { id: 'leo', name: 'Leo' },
};

// Legacy source/data exports are retained only for old revision fixtures and
// compatibility tests. New spaces never receive this authored studio.
export const initialState = {
  projects: [
    { id: 'tidepool', title: 'Tidepool', description: 'A little closer to nature.', color: '#567764' },
    { id: 'afterhours', title: 'After Hours', description: 'A listening room for night owls.', color: '#aa684d' },
    { id: 'smallhours', title: 'Small Hours', description: 'Objects for slower mornings.', color: '#a59d6b' },
  ],
  contributions: [],
  extras: {},
};

export const seedSource = `export const meta = {
  title: "A few things taking shape",
  subtitle: "An open studio for the things I want to bring into the world.",
  accent: "#04b84c"
};

export function render(state, actor) {
  return '<style>.studio-note{margin:26px 0 4px;text-align:center;color:#a3a3a3;font:17px Arial,Helvetica,sans-serif;line-height:1.6}</style><p class="studio-note">Good things begin with a little room to play.</p>';
}

export function reduce(state, action, actor) {
  throw new Error("There is nothing to do here just yet.");
}
`;

export const seedTests = `export function runTests(api) {
  const actor = { id: "studio-test", name: "Studio guest" };
  const before = JSON.stringify(api.initialState);
  const html = api.render(api.initialState, actor);
  let refusesUnknownAction = false;
  try { api.reduce(api.initialState, { type: "unknown" }, actor); }
  catch { refusesUnknownAction = true; }
  return [
    { name: "The open studio welcomes its visitors", ok: html.includes("room to play") },
    { name: "All three original projects remain", ok: api.initialState.projects.length === 3 },
    { name: "Viewing leaves the saved state intact", ok: before === JSON.stringify(api.initialState) },
    { name: "Unknown actions cannot alter the studio", ok: refusesUnknownAction }
  ];
}
`;

// New accounts and individual owner resets use this empty canvas. A normal
// builder turn creates their page. The directory may opt a brand-new example
// store into a verified initial page; reopening never replaces saved code.
export const blankInitialState = { projects: [], contributions: [], extras: {} };

// This exact source is a persisted blank-canvas sentinel, including its unused
// accent. Keep it stable: changing cosmetic metadata would make existing blank
// accounts look built to the directory, preview and icon-generation paths.
export const blankSeedSource = `export const meta = {
  title: "A space for your next idea",
  subtitle: "",
  accent: "#687957"
};
export function render(state, actor) { return ''; }
export function reduce(state, action, actor) {
  throw new Error("Your space is ready for its first idea.");
}
`;

export const blankSeedTests = `export function runTests(api) {
  const actor = { id: "blank-test", name: "New visitor" };
  const before = JSON.stringify(api.initialState);
  const html = api.render(api.initialState, actor);
  let blocked = false;
  try { api.reduce(api.initialState, { type: "unknown" }, actor); }
  catch { blocked = true; }
  return [
    { name: "A new space begins with an empty canvas", ok: html === '' },
    { name: "The empty canvas does not insert starter projects", ok: api.initialState.projects.length === 0 },
    { name: "Viewing preserves every saved field", ok: before === JSON.stringify(api.initialState) },
    { name: "An unbuilt canvas cannot accept actions", ok: blocked }
  ];
}
`;

export function seedFor(kind = 'studio') {
  if (kind !== 'blank' && kind !== 'studio') throw new Error('Unknown space kind.');
  return { state: structuredClone(blankInitialState), source: blankSeedSource, tests: blankSeedTests };
}
