const state = {
  config: null,
  incident: null,
  mode: 'guided',
  busy: false,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function delay(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function requestJSON(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || 'The request could not be completed.');
  return payload;
}

function setConnection(label, status = 'ready') {
  const node = $('#connection-status');
  node.classList.toggle('is-busy', status === 'busy');
  node.classList.toggle('is-error', status === 'error');
  node.lastChild.textContent = ` ${label}`;
}

function showToast(message) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => { toast.hidden = true; }, 6500);
}

function setBusy(busy, label = 'Ready') {
  state.busy = busy;
  $$('.mode-option, #start-button, #reset-button, #command-input, #command-form button, .suggestion-button').forEach((control) => {
    control.disabled = busy || control.dataset.locked === 'true';
  });
  $('#agent-state').textContent = busy ? label : state.incident ? 'Monitoring active incident' : 'Waiting for shift';
  setConnection(busy ? label : state.mode === 'live' ? 'Live Agents API' : 'Guided simulation', busy ? 'busy' : 'ready');
}

function formatDecision(value) {
  return {
    restock_from_backroom: 'Restock from back room',
    request_store_transfer: 'Request a nearby-store transfer',
    wait_for_inbound: 'Wait for the inbound truck',
    needs_human_review: 'Needs manager review',
  }[value] || value.replaceAll('_', ' ');
}

function addMessage(actor, text, evidence = []) {
  const conversation = $('#conversation');
  const row = element('div', `message ${actor}-message`);
  row.append(element('span', null, actor === 'manager' ? 'You · store manager' : actor));
  row.append(element('p', null, text));
  if (evidence.length) {
    const list = element('ul', 'message-evidence');
    evidence.forEach((item) => list.append(element('li', null, item)));
    row.append(list);
  }
  conversation.append(row);
  conversation.scrollTop = conversation.scrollHeight;
  return row;
}

function addThinking() {
  const row = addMessage('agent', 'Checking store systems');
  row.classList.add('is-thinking');
  return row;
}

function renderCases(container, count, className, maximum) {
  container.replaceChildren();
  for (let index = 0; index < maximum; index += 1) {
    const box = element('span', `${className}${index < count ? '' : ' is-empty'}`);
    box.setAttribute('aria-hidden', 'true');
    container.append(box);
  }
}

function renderStore(snapshot) {
  const inventory = snapshot.inventory;
  renderCases($('#scene-shelf'), inventory.shelf_units, 'shelf-box', inventory.shelf_capacity);
  renderCases($('#backroom-stack'), inventory.backroom_units, 'stock-box', 24);
  $('#shelf-metric').textContent = `${inventory.shelf_units} / ${inventory.shelf_capacity}`;
  $('#backroom-metric').textContent = `${inventory.backroom_units} units`;
  $('#demand-metric').textContent = `${snapshot.forecast.forecast_units} units`;
  $('#demand-label').textContent = snapshot.forecast.units_already_sold ? 'Remaining demand' : '24h demand';
  $('#truck-metric').textContent = snapshot.shipment.delay_hours ? `+${snapshot.shipment.delay_hours}h` : 'On time';
  $('#nearby-metric').textContent = `${snapshot.nearby.available_transfer_units} units`;
  $('#store-scene').classList.toggle('has-storm', snapshot.weather.active);
}

function renderTimeline(log) {
  const timeline = $('#manager-timeline');
  timeline.replaceChildren();
  if (!log.length) {
    timeline.append(element('li', 'muted-row', 'No incident activity yet.'));
    return;
  }
  log.forEach((entry) => {
    const row = element('li');
    row.append(element('b', null, entry.actor), element('span', null, entry.action));
    timeline.append(row);
  });
}

function renderTools(incident) {
  const list = $('#tool-list');
  list.replaceChildren();
  const turns = [
    ['Low shelf', incident.initial_turn],
    ['Storm event', incident.storm_turn],
  ].filter(([, turn]) => turn);
  const calls = turns.flatMap(([stage, turn]) => turn.tool_calls.map((call) => ({ stage, call })));
  calls.forEach(({ stage, call }) => {
    const details = element('details', 'tool-row');
    const summary = element('summary');
    summary.append(
      element('strong', null, call.name),
      element('span', null, JSON.stringify(call.arguments)),
      element('small', null, stage),
    );
    const output = element('pre', 'tool-output');
    output.textContent = JSON.stringify(call.output, null, 2);
    details.append(summary, output);
    list.append(details);
  });
  if (!calls.length) list.append(element('p', 'muted-row', 'Agent tool calls will appear here.'));

  const trace = $('#trace-identifiers');
  trace.hidden = !turns.length;
  trace.replaceChildren();
  turns.forEach(([stage, turn]) => trace.append(element('span', null, `${stage}: ${turn.turn_id}`)));
  if (turns.length) trace.append(element('span', null, `Session: ${incident.initial_turn.session_id}`));
  const traceUrl = incident.storm_turn?.trace_url || incident.initial_turn.trace_url;
  $('#trace-button').disabled = !traceUrl;
  $('#trace-button').onclick = traceUrl ? () => window.open(traceUrl, '_blank', 'noopener') : null;
}

function recommendationFor(incident) {
  if (incident.stage === 'initial_review') return incident.initial_turn;
  if (incident.stage === 'storm_review' || incident.stage === 'resolved') return incident.storm_turn;
  return null;
}

function showSceneAlert(incident) {
  const alert = $('#scene-alert');
  const turn = recommendationFor(incident);
  const weatherPending = incident.stage === 'restock_approved';
  const visible = weatherPending || (Boolean(turn) && incident.stage !== 'resolved');
  alert.hidden = !visible;
  $('#unread-badge').hidden = !visible;
  if (!visible) return;
  if (weatherPending) {
    $('#scene-alert-title').textContent = 'Severe weather event detected';
    $('#scene-alert-copy').textContent = 'Storm risk may delay the next truck. Check this event.';
    return;
  }
  $('#scene-alert-title').textContent = formatDecision(turn.decision.decision);
  $('#scene-alert-copy').textContent = `${turn.decision.quantity} units · manager response requested`;
}

function renderSuggestions(stage) {
  const suggestions = $('#suggestions');
  suggestions.replaceChildren();
  const commands = {
    initial_review: ['Approve the shelf restock'],
    restock_approved: ['Check the weather event'],
    storm_review: ['Approve this transfer', 'Escalate to regional operations'],
    resolved: [],
  }[stage] || [];
  commands.forEach((command) => {
    const button = element('button', 'suggestion-button', command);
    button.type = 'button';
    button.addEventListener('click', () => sendManagerCommand(command));
    suggestions.append(button);
  });
  const input = $('#command-input');
  const enabled = Boolean(state.incident) && stage !== 'resolved';
  input.disabled = !enabled || state.busy;
  $('#command-form button').disabled = !enabled || state.busy;
  input.placeholder = enabled ? 'Type an instruction, for example: approve this transfer' : 'Start a new shift to issue commands';
}

function renderStage(incident) {
  const labels = {
    initial_review: 'Agent alert · low shelf',
    restock_approved: 'Weather alert · action needed',
    storm_review: 'Agent alert · storm',
    resolved: 'Incident resolved',
  };
  $('#stage-pill').textContent = labels[incident.stage];
  const floorCopy = {
    initial_review: 'Maya is waiting for the manager decision.',
    restock_approved: 'Shelf is healthy. A severe storm may delay the next truck.',
    storm_review: 'Luis is holding Dock 2 for a possible transfer.',
    resolved: incident.resolution === 'approved'
      ? `Truck unloaded ${incident.transfer_received} cases; Maya restored the aisle with ${incident.follow_up_restock}.`
      : 'Regional operations is reviewing the incident.',
  };
  $('#floor-status').textContent = floorCopy[incident.stage];
  const weatherActive = ['restock_approved', 'storm_review', 'resolved'].includes(incident.stage);
  document.body.classList.toggle('weather-active', weatherActive);
  $('#store-scene').classList.toggle('has-storm', weatherActive);
  $('#disruption-panel').hidden = incident.stage !== 'restock_approved';
  $('#transfer-load').classList.toggle(
    'is-arriving',
    incident.stage === 'resolved' && incident.resolution === 'approved' && incident.storm_turn?.decision.decision === 'request_store_transfer',
  );
}

function renderIncident(incident) {
  state.incident = incident;
  renderStore(incident.snapshot);
  renderStage(incident);
  renderTimeline(incident.manager_log);
  renderTools(incident);
  renderSuggestions(incident.stage);
  showSceneAlert(incident);
  $('#start-button').hidden = true;
  $('#reset-button').disabled = state.busy;
  $('#reset-button').dataset.locked = 'false';
}

function describeRecommendation(turn) {
  return `${formatDecision(turn.decision.decision)}: ${turn.decision.quantity} units. ${turn.decision.summary}`;
}

async function animateRestock(quantity) {
  const scene = $('#store-scene');
  const shelfSlots = [...$('#scene-shelf').querySelectorAll('.shelf-box.is-empty')];
  const backroomCases = [...$('#backroom-stack').querySelectorAll('.stock-box:not(.is-empty)')].reverse();
  const startingShelf = $('#scene-shelf').childElementCount - shelfSlots.length;
  const startingBackroom = backroomCases.length;
  const sceneRect = scene.getBoundingClientRect();
  const movements = [];

  scene.classList.add('is-restocking');
  for (let index = 0; index < quantity; index += 1) {
    const source = backroomCases[index];
    const target = shelfSlots[index];
    if (!source || !target) break;
    const sourceRect = source.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const movingCase = element('span', 'flying-case');
    movingCase.style.left = `${sourceRect.left - sceneRect.left}px`;
    movingCase.style.top = `${sourceRect.top - sceneRect.top}px`;
    movingCase.style.width = `${sourceRect.width}px`;
    movingCase.style.height = `${sourceRect.height}px`;
    scene.append(movingCase);
    source.classList.add('is-empty');

    const movement = movingCase.animate(
      [
        { transform: 'translate(0, 0) scale(1)', offset: 0 },
        { transform: `translate(-28px, ${Math.min(90, targetRect.top - sourceRect.top)}px) scale(1.08)`, offset: .28 },
        { transform: `translate(${targetRect.left - sourceRect.left}px, ${targetRect.top - sourceRect.top}px) scale(1)`, offset: 1 },
      ],
      { duration: 760, delay: index * 105, easing: 'cubic-bezier(.35,.72,.35,1)', fill: 'forwards' },
    ).finished.then(() => {
      target.classList.remove('is-empty');
      movingCase.remove();
      const completed = index + 1;
      $('#shelf-metric').textContent = `${startingShelf + completed} / 24`;
      $('#backroom-metric').textContent = `${startingBackroom - completed} units`;
      $('#floor-status').textContent = `Maya stocked ${completed} of ${quantity} approved cases.`;
    });
    movements.push(movement);
  }
  await Promise.all(movements);
  scene.classList.remove('is-restocking');
}

async function animateStormSales(quantity) {
  const visibleCases = [...$('#scene-shelf').querySelectorAll('.shelf-box:not(.is-empty)')].reverse();
  const startingShelf = visibleCases.length;
  $('#floor-status').textContent = 'Storm demand is drawing down the water aisle.';
  for (let index = 0; index < quantity; index += 1) {
    const shelfCase = visibleCases[index];
    if (!shelfCase) break;
    shelfCase.style.transform = 'translateY(-8px) scale(.85)';
    await delay(55);
    shelfCase.classList.add('is-empty');
    shelfCase.style.transform = '';
    $('#shelf-metric').textContent = `${startingShelf - index - 1} / 24`;
    $('#floor-status').textContent = `Storm demand sold ${index + 1} of ${quantity} cases.`;
  }
}

async function animateTransferFulfillment(result) {
  const scene = $('#store-scene');
  const transferQuantity = result.incident.transfer_received;
  const restockQuantity = result.incident.follow_up_restock;
  const startingNearby = state.incident.snapshot.nearby.available_transfer_units;
  scene.classList.add('is-transfering');
  $('#transfer-load').classList.add('is-arriving');
  $('#floor-status').textContent = `Store 205 truck is arriving with ${transferQuantity} cases.`;
  await delay(1500);

  const inventory = state.incident.snapshot.inventory;
  renderCases($('#backroom-stack'), inventory.backroom_units, 'stock-box', 32);
  const backroomSlots = [...$('#backroom-stack').querySelectorAll('.stock-box.is-empty')];
  const sceneRect = scene.getBoundingClientRect();
  const dockRect = $('#transfer-load').getBoundingClientRect();
  const movements = [];
  for (let index = 0; index < transferQuantity; index += 1) {
    const target = backroomSlots[index];
    if (!target) break;
    const targetRect = target.getBoundingClientRect();
    const movingCase = element('span', 'flying-case');
    movingCase.style.left = `${dockRect.left - sceneRect.left + dockRect.width / 2}px`;
    movingCase.style.top = `${dockRect.top - sceneRect.top + dockRect.height / 2}px`;
    movingCase.style.width = `${Math.max(10, targetRect.width)}px`;
    movingCase.style.height = `${Math.max(8, targetRect.height)}px`;
    scene.append(movingCase);
    const movement = movingCase.animate(
      [
        { transform: 'translate(0, 0) scale(.85)', offset: 0 },
        { transform: `translate(${targetRect.left - dockRect.left - dockRect.width / 2}px, ${targetRect.top - dockRect.top - dockRect.height / 2}px) scale(1)`, offset: 1 },
      ],
      { duration: 520, delay: index * 48, easing: 'ease-out', fill: 'forwards' },
    ).finished.then(() => {
      target.classList.remove('is-empty');
      movingCase.remove();
      const completed = index + 1;
      $('#backroom-metric').textContent = `${inventory.backroom_units + completed} units`;
      $('#nearby-metric').textContent = `${startingNearby - completed} units`;
      $('#floor-status').textContent = `Luis unloaded ${completed} of ${transferQuantity} cases into the back room.`;
    });
    movements.push(movement);
  }
  await Promise.all(movements);
  $('#floor-status').textContent = 'Truck unloaded. Maya is replenishing the aisle.';
  await animateRestock(restockQuantity);
  scene.classList.remove('is-transfering');
}

async function animateAction(intent, result) {
  if (intent === 'approve_restock') {
    await animateRestock(result.incident.approved_restock);
  } else if (intent === 'report_storm') {
    await animateStormSales(result.incident.storm_sales);
  } else if (intent === 'approve_transfer') {
    await animateTransferFulfillment(result);
  }
}

function resolveShelfAlert() {
  const firstAlert = $('#conversation').querySelector('.system-message');
  if (firstAlert) {
    firstAlert.classList.add('is-resolved');
    firstAlert.querySelector('p').textContent = 'Resolved: shelf recovered to 20 of 24 units.';
  }
  const firstRecommendation = $('#conversation').querySelector('.agent-message');
  if (firstRecommendation) {
    firstRecommendation.classList.add('is-resolved');
    firstRecommendation.querySelector('span').textContent = 'Agent · completed action';
    firstRecommendation.querySelector('p').textContent = 'Completed: 16 cases moved from the back room to the shelf.';
    firstRecommendation.querySelector('.message-evidence')?.remove();
  }
  addMessage('system', 'Weather alert: a severe storm may delay the next replenishment truck.');
}

async function startIncident() {
  if (state.busy) return;
  setBusy(true, state.mode === 'live' ? 'Live agent checking store' : 'Agent checking store');
  $('#conversation').replaceChildren();
  addMessage('system', 'Low-shelf sensor: bottled water has fallen below the presentation threshold.');
  const thinking = addThinking();
  try {
    const incident = await requestJSON('/api/incidents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: state.mode }),
    });
    thinking.remove();
    renderIncident(incident);
    addMessage('agent', describeRecommendation(incident.initial_turn), incident.initial_turn.decision.evidence_used);
  } catch (error) {
    thinking.remove();
    addMessage('agent', `I could not complete the review: ${error.message}`);
    setConnection('Needs attention', 'error');
  } finally {
    setBusy(false);
    if (state.incident) renderSuggestions(state.incident.stage);
  }
}

async function sendManagerCommand(command) {
  const trimmed = command.trim();
  if (!trimmed || state.busy || !state.incident) return;
  addMessage('manager', trimmed);
  $('#command-input').value = '';
  const thinking = addThinking();
  if (state.incident.stage === 'restock_approved') $('#store-scene').classList.add('has-storm');
  setBusy(true, state.incident.stage === 'restock_approved' ? 'Same agent reassessing' : 'Recording manager decision');
  try {
    const result = await requestJSON(`/api/incidents/${state.incident.incident_id}/manager-command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        command: trimmed,
        delay_hours: Number($('#delay-control').value),
        demand_units: Number($('#demand-control').value),
        nearby_units: Number($('#nearby-control').value),
      }),
    });
    thinking.remove();
    if (result.accepted) await animateAction(result.intent, result);
    renderIncident(result.incident);
    if (result.intent === 'approve_restock') resolveShelfAlert();
    const turn = recommendationFor(result.incident);
    const response = result.intent === 'report_storm' && turn
      ? `${result.reply} ${describeRecommendation(turn)}`
      : result.reply;
    addMessage('agent', response, result.intent === 'report_storm' && turn ? turn.decision.evidence_used : []);
  } catch (error) {
    thinking.remove();
    addMessage('agent', `I could not apply that instruction: ${error.message}`);
    setConnection('Needs attention', 'error');
  } finally {
    setBusy(false);
    if (state.incident) renderSuggestions(state.incident.stage);
  }
}

function updateScenarioLabels() {
  $('#delay-value').textContent = `${$('#delay-control').value}h`;
  $('#demand-value').textContent = $('#demand-control').value;
  $('#nearby-value').textContent = $('#nearby-control').value;
}

function resetView() {
  state.incident = null;
  renderStore(state.config.snapshot);
  $('#store-scene').classList.remove('has-storm', 'is-restocking', 'is-transfering');
  document.body.classList.remove('weather-active');
  $('#transfer-load').classList.remove('is-arriving');
  $('#scene-alert').hidden = true;
  $('#unread-badge').hidden = true;
  $('#stage-pill').textContent = 'Shift not started';
  $('#floor-status').textContent = 'Team is ready for the morning shift.';
  $('#disruption-panel').hidden = true;
  $('#start-button').hidden = false;
  $('#reset-button').disabled = true;
  $('#reset-button').dataset.locked = 'true';
  $('#conversation').replaceChildren();
  addMessage('agent', 'Start the shift and I will watch inventory, demand, shipments, weather, and store policy.');
  renderTimeline([]);
  $('#tool-list').replaceChildren(element('p', 'muted-row', 'Agent tool calls will appear here.'));
  $('#trace-identifiers').hidden = true;
  $('#trace-button').disabled = true;
  renderSuggestions(null);
}

async function resetIncident() {
  if (state.busy) return;
  setBusy(true, 'Opening a new shift');
  try {
    if (state.incident) await requestJSON(`/api/incidents/${state.incident.incident_id}`, { method: 'DELETE' });
    resetView();
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(false);
  }
}

async function changeMode(mode) {
  if (state.busy || mode === state.mode) return;
  if (state.incident) await resetIncident();
  if (mode === 'live' && !state.config.live_available) {
    showToast('Live mode needs OPENAI_API_KEY in the server environment.');
    return;
  }
  state.mode = mode;
  $$('.mode-option').forEach((button) => button.classList.toggle('is-active', button.dataset.mode === mode));
  setConnection(mode === 'live' ? 'Live Agents API' : 'Guided simulation');
}

async function initialize() {
  try {
    state.config = await requestJSON('/api/config');
    resetView();
    setConnection('Guided simulation');
  } catch (error) {
    setConnection('Server unavailable', 'error');
    showToast(error.message);
  }
}

$('#start-button').addEventListener('click', startIncident);
$('#reset-button').addEventListener('click', resetIncident);
$('#command-form').addEventListener('submit', (event) => {
  event.preventDefault();
  sendManagerCommand($('#command-input').value);
});
$$('.mode-option').forEach((button) => button.addEventListener('click', () => changeMode(button.dataset.mode)));
['#delay-control', '#demand-control', '#nearby-control'].forEach((selector) => $(selector).addEventListener('input', updateScenarioLabels));

initialize();
