// Dependency-free smoke test for the standalone renderer and its event handlers.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const html = fs.readFileSync(process.argv[2], "utf8");
const payload = JSON.parse(html.match(/<script id="viewer-data" type="application\/json">([\s\S]*?)<\/script>/)[1]);
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

class Element {
  constructor(tag) {
    this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {}; this.style = {};
    this.attributes = {}; this.listeners = {}; this.className = ""; this.ownText = "";
    this.classList = { toggle: (name, enabled) => {
      const names = new Set(this.className.split(/\s+/).filter(Boolean));
      if (enabled === undefined) enabled = !names.has(name);
      if (enabled) names.add(name); else names.delete(name);
      this.className = [...names].join(" "); return enabled;
    }, contains: name => this.className.split(/\s+/).includes(name) };
  }
  set textContent(text) { this.ownText = String(text); this.children = []; }
  get textContent() { return this.ownText + this.children.map(child => child.textContent).join(""); }
  appendChild(child) { this.children.push(child); child.parentElement = this; return child; }
  replaceChildren(...children) { this.children = []; children.forEach(child => this.appendChild(child)); }
  setAttribute(name, value) { this.attributes[name] = String(value); if (name === "class") this.className = value; }
  getAttribute(name) { return this.attributes[name] ?? null; }
  addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
  dispatch(name, event = {}) {
    event = { target: this, preventDefault() {}, stopPropagation() {}, ...event };
    for (const callback of this.listeners[name] || []) callback(event);
  }
  matches(selector) {
    return selector.split(",").some(part => {
      part = part.trim();
      if (part.startsWith(".")) return this.classList.contains(part.slice(1));
      if (part.startsWith("#")) return this.id === part.slice(1);
      if (part.startsWith("[data-")) {
        const key = part.slice(6, -1).replace(/-([a-z])/g, (_, char) => char.toUpperCase());
        return this.dataset[key] !== undefined;
      }
      return this.tagName === part.toUpperCase();
    });
  }
  closest(selector) { return this.matches(selector) ? this : this.parentElement?.closest(selector) || null; }
  querySelectorAll(selector) {
    return this.children.flatMap(child => [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  getBoundingClientRect() { return { left: 0, top: 0, width: 960, height: 30 }; }
  scrollIntoView() { this.scrolled = true; }
  focus() { document.activeElement = this; }
}

const root = new Element("body");
for (const [, tag, id] of html.matchAll(/<(\w+)[^>]*\bid="([^"]+)"/g)) {
  const element = new Element(tag); element.id = id; root.appendChild(element);
}
const document = {
  getElementById: id => root.querySelectorAll("#" + id)[0] || null,
  createElement: tag => new Element(tag), createElementNS: (_, tag) => new Element(tag),
  addEventListener() {}, activeElement: null
};

// Add two overlapping, same-name calls to exercise exact marker navigation.
const scenario = payload.scenarios[0];
scenario.finalMetrics.audio.metrics_version = "2.0";
scenario.turns = [{role: "caller", startMs: 0, endMs: 80, text: "Please look that up."},
  {role: "assistant", startMs: 200, endMs: 900, text: "Let me check. Here is the result."}];
scenario.delegations = [{timeMs: 100, target: "client", status: "completed", responseCount: 1,
  responses: ["Done."], toolCount: 2, tools: [{name: "lookup", status: "completed", toolIndex: 0},
    {name: "lookup", status: "failed", toolIndex: 1}]}];
scenario.toolCalls = [{timeMs: 250, name: "lookup", status: "completed", arguments: {date: "first"}, delegationIndex: 0},
  {timeMs: 300, name: "lookup", status: "failed", arguments: {date: "second"}, delegationIndex: 0}];
scenario.eventAnnotations = [{timeMs: 100, kind: "delegation", label: "Delegation · client", delegationIndex: 0},
  {timeMs: 250, kind: "tool", label: "lookup", status: "completed", toolIndex: 0},
  {timeMs: 300, kind: "tool", label: "lookup", status: "failed", toolIndex: 1}];
document.getElementById("viewer-data").textContent = JSON.stringify(payload);
const audio = document.getElementById("conversation-audio");
Object.assign(audio, {paused: true, currentTime: 0, pause() { this.paused = true; }, play() { this.paused = false; return Promise.resolve(); }});
vm.runInNewContext(script, {document, window: {matchMedia: () => ({matches: false}), addEventListener() {}},
  requestAnimationFrame: () => 1, cancelAnimationFrame() {}});

const transcript = document.getElementById("transcript-list");
assert.equal(transcript.querySelectorAll(".backend-row").length, 3);
assert.ok(transcript.querySelectorAll("details").every(item => !item.open), "backend details start collapsed");
assert.equal(transcript.children.length, 2, "the conversation contains speech turns, not interleaved backend events");
const responseGroup = transcript.children[1];
assert.equal(responseGroup.children[0].classList.contains("transcript-row"), true, "speech is displayed first");
assert.deepEqual(responseGroup.querySelectorAll(".backend-row").map(row => row.id),
  ["activity-delegation-0", "activity-tool-0", "activity-tool-1"], "related activity follows the response");
assert.equal(document.getElementById("activity-delegation-0").closest(".transcript-row"), null,
  "activity controls are not nested inside the speech seek button");
const markers = document.getElementById("events-track").querySelectorAll(".event-marker");
for (const [index, expected, time] of [[0, "activity-delegation-0", .1], [1, "activity-tool-0", .25], [2, "activity-tool-1", .3]]) {
  markers[index].dispatch("click");
  const row = document.getElementById(expected);
  assert.equal(row.querySelector("details").open, true);
  assert.equal(row.scrolled, true);
  assert.equal(document.activeElement, row.querySelector("summary"));
  assert.equal(row.classList.contains("is-selected"), true);
  assert.equal(audio.currentTime, time);
}
assert.match(document.getElementById("activity-tool-1").textContent, /second/);

const renderedPaths = new Set(document.getElementById("metric-list").querySelectorAll(".metric-row").map(row => row.dataset.metricPath));
function checkMetrics(value, path) {
  if (path.join(".") === "audio.metrics_version") return;
  if (value && typeof value === "object" && !("actual" in value && "expected" in value) && Object.keys(value).length) {
    for (const [key, child] of Object.entries(value)) checkMetrics(child, path.concat(key));
  } else assert.ok(renderedPaths.has(path.join(".")), "missing metric: " + path.join("."));
}
checkMetrics(scenario.finalMetrics, []);
assert.equal(renderedPaths.has("audio.metrics_version"), false, "schema version is not a customer-facing signal");
assert.equal(scenario.finalMetrics.audio.metrics_version, "2.0", "schema metadata remains in the saved evidence");
assert.match(document.getElementById("metric-list").textContent, /Actual \/ expected/);
console.log("Viewer DOM: response-grouped activity, exact marker navigation, and visible signal fields passed.");
