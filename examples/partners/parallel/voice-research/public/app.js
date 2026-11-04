const $ = selector => document.querySelector(selector);
let pc, channel, input, context, eventSource, recorder, merger, destination;
let sessionId = '', events = [], recordingBlob = null, recordingStart = 0, closed = false;
let closing = null, startedResolve, startedReject, startedPromise, stopRecording;
let captionTurns = {};
const cards = new Map();
const record = (type, data) => events.push({ type, data, client_ms: performance.now() });
const status = text => {
  const ended = text.startsWith('Closed');
  $('#status').textContent = ended ? 'Conversation ended' : text;
  $('.bars').classList.toggle('active', text === 'Listening');
  $('#start').hidden = ['Listening', 'Closing'].includes(text);
  $('#stop').hidden = !$('#start').hidden;
  $('#session-hint').textContent = text === 'Listening' ? 'Ask another question or change your request.' : ended ? 'Start a new conversation when you’re ready.' : text === 'Connecting' ? 'Connecting your microphone.' : 'Finishing your conversation.';
};
const error = text => $('#error').textContent = text;

function appendCaption(event) {
  const role = event.type === 'session.input_transcript.delta' ? 'You' : 'Assistant';
  const other = captionTurns[role === 'You' ? 'Assistant' : 'You'];
  const captions = $('#captions');
  const follow = captions.scrollHeight - captions.scrollTop - captions.clientHeight < 40;
  // GPT-Live is full duplex, so each speaker's caption grows on its own during overlap. Deltas include
  // their own spaces and punctuation, even partial words. A new caption starts after a two-second gap
  // or a complete turn by the other speaker; a backchannel keeps growing the current one.
  let turn = captionTurns[role];
  const otherTookTurn = other?.start_ms >= turn?.end_ms && event.start_ms >= other.end_ms;
  if (!turn || event.start_ms - turn.end_ms > 2000 || otherTookTurn) {
    turn = captionTurns[role] = { node: document.createElement('div'), text: '', start_ms: event.start_ms };
    turn.node.className = 'transcript-turn ' + (role === 'You' ? 'user-turn' : 'assistant-turn');
    const label = document.createElement('div'); label.className = 'speaker'; label.textContent = role === 'You' ? 'You' : 'GPT-Live';
    turn.body = document.createElement('p'); turn.node.append(label, turn.body);
    captions.append(turn.node);
  }
  turn.text += event.delta;
  turn.end_ms = event.end_ms;
  turn.body.textContent = turn.text.trimStart();
  if (follow) captions.scrollTop = captions.scrollHeight;
}

function uiEvent(event) {
  record('ui.' + event.type, event.data);
  const data = event.data;
  if (event.type === 'task') {
    const previous = cards.get(data.task_id);
    // Snapshots are cumulative and versioned per task; a lower or equal version is a stale replay.
    if (previous && data.version <= previous.version) return;
    const node = previous?.node ?? document.createElement('article');
    node.className = 'research-card' + (data.state === 'researching' ? ' inprogress' : data.state === 'cancelled' ? ' cancelled' : ''); node.dataset.taskId = data.task_id;
    const top = document.createElement('div'), title = document.createElement('h3'), details = document.createElement('p');
    const state = document.createElement('p'), summary = document.createElement('div');
    const sources = document.createElement('ul');
    top.className = 'top';
    title.textContent = data.display_title || data.task.request;
    details.className = 'task-details';
    const date = data.task.date ? new Date(data.task.date + 'T12:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }) : null;
    details.textContent = [data.task.location, date, ...data.task.constraints].filter(Boolean).join(' · ');
    state.className = 'task-state badge';
    const labels = { researching: data.revision > 1 ? 'Updating' : 'Searching', completed: data.outcome === 'insufficient_evidence' ? 'Not enough evidence' : 'Answer ready', cancelled: 'Cancelled', failed: 'Could not finish' };
    if (data.state === 'researching') { const dot = document.createElement('span'); dot.className = 'dot'; dot.setAttribute('aria-hidden', 'true'); state.append(dot); }
    if (data.state === 'completed' && data.outcome !== 'insufficient_evidence') { const check = document.createElement('span'); check.textContent = '✓'; check.setAttribute('aria-hidden', 'true'); state.append(check); }
    state.append(document.createTextNode(labels[data.state] ?? data.state));
    summary.className = 'task-summary';
    if (data.display_items?.length) {
      const list = document.createElement('ul'); list.className = 'answer-items';
      for (const item of data.display_items) {
        const row = document.createElement('li'), heading = document.createElement('strong'), body = document.createElement('span');
        heading.textContent = item.heading; body.textContent = item.detail;
        row.append(heading, body); list.append(row);
      }
      summary.append(list);
    } else summary.textContent = data.current_summary ?? data.summary;
    sources.className = 'sources';
    const seenUrls = new Set();
    for (const source of data.current_sources ?? data.sources) {
      let url; try { url = new URL(source.url); } catch { continue; }
      if (!['http:', 'https:'].includes(url.protocol) || seenUrls.has(url.href)) continue;
      seenUrls.add(url.href);
      const li = document.createElement('li'), a = document.createElement('a'), icon = document.createElement('span');
      const copy = document.createElement('div'), publisher = document.createElement('b'), pageTitle = document.createElement('span'), arrow = document.createElement('div');
      li.className = 'source'; a.className = 'source';
      a.href = url.href; a.target = '_blank'; a.rel = 'noopener noreferrer';
      const host = url.hostname.replace(/^www\./, '');
      icon.className = 'source-initial'; icon.textContent = host.slice(0, 1).toUpperCase(); icon.setAttribute('aria-hidden', 'true');
      copy.className = 'source-copy'; publisher.textContent = source.title || url.pathname; pageTitle.textContent = host;
      copy.append(publisher, pageTitle); arrow.className = 'arrow'; arrow.textContent = '↗'; arrow.setAttribute('aria-hidden', 'true');
      a.append(icon, copy, arrow); li.append(a); sources.append(li);
    }
    top.append(title, state);
    node.replaceChildren(top, details, summary, sources);
    if (!previous) { $('#empty-research')?.remove(); $('#research').prepend(node); }
    cards.set(data.task_id, { ...data, node });
    $('#request-count').textContent = `${cards.size} ${cards.size === 1 ? 'request' : 'requests'}`;
  }
  if (event.type === 'error') {
    error(data.message);
    if (data.fatal) void close();
  }
}

async function start({ capture = false } = {}) {
  if (pc) return;
  recorder = null; context = null; recordingStart = 0;
  sessionId = ''; events = []; recordingBlob = null; closing = null; closed = false; captionTurns = {};
  error(''); cards.clear(); $('#research').replaceChildren(); $('#captions').replaceChildren();
  $('#request-count').textContent = '0 requests';

  $('#assistant').controls = false; $('#assistant').hidden = true;
  $('#start').disabled = true; status('Connecting');
  startedPromise = new Promise((resolve, reject) => { startedResolve = resolve; startedReject = reject; });
  void startedPromise.catch(() => {});
  try {
    if (capture) { context = new AudioContext(); await context.resume(); }
    input = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true } });
    if (capture) {
    merger = context.createChannelMerger(2); destination = context.createMediaStreamDestination();
    context.createMediaStreamSource(input).connect(merger, 0, 0); merger.connect(destination);
    if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
      const chunks = [];
      recorder = new MediaRecorder(destination.stream, { mimeType: 'audio/webm;codecs=opus' });
      recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      stopRecording = new Promise(resolve => {
        recorder.onstop = () => { recordingBlob = new Blob(chunks, { type: recorder.mimeType }); resolve(); };
      });
      recordingStart = performance.now(); recorder.start();
    }
    }
    pc = new RTCPeerConnection(); input.getTracks().forEach(track => pc.addTrack(track, input));
    pc.ontrack = event => {
      const stream = new MediaStream([event.track]);
      // Play through the media element, the WebRTC playout path that browser echo cancellation
      // subtracts from the microphone. WebAudio only feeds the recording's second channel.
      const audio = $('#assistant'); audio.srcObject = stream;
      void audio.play().catch(() => {
        audio.controls = true; audio.hidden = false;
        error('Select play on the audio controls to hear the assistant.');
      });
      if (capture) context.createMediaStreamSource(stream).connect(merger, 0, 1);
    };
    channel = pc.createDataChannel('oai-events');
    channel.onmessage = ({ data }) => {
      let event; try { event = JSON.parse(data); } catch { return; }
      record('live.event', event);
      // Rejecting a settled startup promise is a no-op, so these only matter before session.started.
      if (event.type === 'session.started') startedResolve();
      if (event.type === 'session.closed') {
        closed = true; startedReject(new Error('Session closed before startup.')); void close();
      }
      if (event.type === 'error') {
        error(event.error?.message ?? 'Voice error.');
        startedReject(new Error(event.error?.message ?? 'Startup failed.'));
      }
      if (event.type.endsWith('transcript.delta')) appendCaption(event);
    };
    channel.onclose = () => { void close(); };
    pc.onconnectionstatechange = () => {
      if (pc?.connectionState === 'failed') { error('Voice connection failed.'); void close(); }
    };
    await pc.setLocalDescription(await pc.createOffer());
    if (pc.iceGatheringState !== 'complete') await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('ICE gathering timed out.')), 10_000);
      pc.addEventListener('icegatheringstatechange', () => {
        if (pc.iceGatheringState === 'complete') { clearTimeout(timer); resolve(); }
      });
    });
    const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const response = await fetch('/api/session', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sdp: pc.localDescription.sdp, timeZone }), signal: AbortSignal.timeout(40_000),
    });
    const result = await response.json(); if (!response.ok) throw new Error(result.error);
    sessionId = result.session.id;
    eventSource = new EventSource('/api/events?id=' + encodeURIComponent(sessionId));
    eventSource.onmessage = event => uiEvent(JSON.parse(event.data));
    eventSource.onerror = () => {
      if (closing) return;
      error('Lost the app connection. Closing this session.');
      void close();
    };
    await pc.setRemoteDescription({ type: 'answer', sdp: result.transport.sdp });
    let timer;
    const startupTimeout = new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error('Session startup timed out.')), 20_000);
    });
    try { await Promise.race([startedPromise, startupTimeout]); } finally { clearTimeout(timer); }
    status('Listening'); $('#stop').disabled = false;
  } catch (cause) {
    // A close already in progress has shown its own reason.
    if (!closing || !$('#error').textContent) error(cause.message);
    await close(); throw cause;
  }
}

// Every caller shares one shutdown and waits for its cleanup.
function close() { return closing ??= shutdown(); }

async function shutdown() {
  // Ends a start() still waiting for session.started, so it cannot close a later session.
  startedReject?.(new Error('Session closed before startup.'));
  $('#stop').disabled = true; status('Closing');
  // Leave audio tracks and transports alive until finalization. The server owns session.close and
  // first blocks new task submissions. Closing the peer connection below also ends the session if the
  // server could not.
  let confirmed = closed;
  if (sessionId) {
    try {
      const response = await fetch('/api/close?id=' + encodeURIComponent(sessionId), { method: 'POST', signal: AbortSignal.timeout(18_000) });
      if (!response.ok) throw new Error('Close failed');
      confirmed = (await response.json()).confirmed || confirmed;
    } catch { /* Keep browser confirmation even when the server is unavailable. */ }
  }
  if (recorder?.state === 'recording') { recorder.stop(); await stopRecording; }

  input?.getTracks().forEach(track => track.stop());
  channel?.close(); pc?.close(); eventSource?.close(); await context?.close();
  $('#assistant').srcObject = null;
  closed = confirmed;
  pc = null; $('#start').disabled = false; status(confirmed ? 'Closed' : 'Closed; final usage unconfirmed');
  return { confirmed };
}

function snapshot() { return { sessionId, events, recordingStart, closed }; }
window.cookbook = { start, close, snapshot, recording: async () => {
  if (!recordingBlob) return null;
  const bytes = new Uint8Array(await recordingBlob.arrayBuffer()); let binary = '';
  for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return btoa(binary);
} };
$('#start').onclick = () => { void start().catch(() => {}); };
$('#stop').onclick = () => { void close(); };
