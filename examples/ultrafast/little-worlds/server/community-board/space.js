export const meta = {
  title: 'Town Square',
  subtitle: 'A shared noticeboard for good company and little discoveries.',
  accent: '#04b84c',
  layout: 'canvas',
  suggestions: [
    { label: 'Add a new topic', prompt: 'Add a topic for local events to this shared message board. Preserve every existing topic, post and participant.' },
    { label: 'Add replies', prompt: 'Let people reply to each other’s messages in Town Square. Keep replies owned by their authors and preserve all existing posts.' },
  ],
};

const topics = [
  { id: 'introductions', label: 'Introductions', color: '#ff8549', description: 'A hello, a little about you, a reason to stay.' },
  { id: 'ideas', label: 'Ideas', color: '#04b84c', description: 'Something you would love to make happen.' },
  { id: 'questions', label: 'Questions', color: '#006aff', description: 'Ask around. Someone might know just the thing.' },
  { id: 'recommendations', label: 'Recommendations', color: '#924ff7', description: 'Books, places and small discoveries worth sharing.' },
];

function escape(value) {
  return String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
}
function action(value) { return escape(JSON.stringify(value)); }
function topicFor(id) { return topics.find(topic => topic.id === id); }
function messagesFor(state) { return Object.entries(state.extras.boardMessages || {}); }

export function render(state, actor) {
  const messages = messagesFor(state);
  const selected = state.extras.boardPreferences?.[actor.id]?.topicId || 'all';
  const topic = topicFor(selected);
  const visible = messages.filter(([, message]) => !topic || message.topicId === selected)
    .sort((left, right) => right[1].sequence - left[1].sequence);
  const ownLast = messages.reduce((last, [, message]) => message.actorId === actor.id ? Math.max(last, message.sequence) : last, 0);
  const pills = [{ id: 'all', label: 'All topics', color: '#ffffff' }, ...topics].map(item => {
    const count = messages.filter(([, message]) => item.id === 'all' || message.topicId === item.id).length;
    return '<button type="button" class="topic' + (selected === item.id ? ' selected' : '') + '" aria-pressed="' + (selected === item.id) + '" data-action="' + action({ type: 'select_topic', topicId: item.id }) + '"><span class="topic-dot" style="background:' + item.color + '"></span>' + item.label + '<span class="topic-count">' + count + '</span></button>';
  }).join('');
  const cards = visible.map(([id, message]) => {
    const category = topicFor(message.topicId);
    return '<article class="message" data-key="message-' + escape(id) + '"><div class="message-top"><span class="message-topic" style="--topic-color:' + (category?.color || '#ffffff') + '">' + escape(category?.label || 'Conversation') + '</span><span class="message-number">' + String(message.sequence).padStart(2, '0') + '</span></div><p class="message-body">' + escape(message.body) + '</p><footer><span class="author"><span class="author-initial">' + escape(message.authorName.slice(0, 1).toUpperCase()) + '</span>' + escape(message.authorName) + (message.actorId === actor.id ? '<span class="you">you</span>' : '') + '</span>' + (message.actorId === actor.id ? '<button type="button" class="remove-message" aria-label="Remove your message: ' + escape(message.body.slice(0, 36)) + '" data-action="' + action({ type: 'delete_message', messageId: id }) + '">Remove</button>' : '') + '</footer></article>';
  }).join('');
  const options = topics.map(item => '<option value="' + item.id + '"' + ((topic?.id || 'introductions') === item.id ? ' selected' : '') + '>' + item.label + '</option>').join('');
  return `<style>
    *{box-sizing:border-box}body{margin:0}.square{--ink:#fff;--muted:#a3a3a3;--paper:#080808;--surface:#141414;--line:#303030;--green:#04b84c;--violet:#924ff7;max-width:1160px;margin:0 auto;padding:48px 42px 60px;color:var(--ink);background:var(--paper);font-family:system-ui,Arial,Helvetica,sans-serif;border:1px solid var(--line);border-radius:4px;color-scheme:dark}
    .square-header{display:flex;justify-content:space-between;gap:30px;align-items:flex-end;padding-bottom:30px;border-bottom:1px solid var(--line)}.eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#57dc8c;margin:0 0 14px;font-weight:600}.square h1{font:500 clamp(40px,7vw,78px)/.97 system-ui,Arial,Helvetica,sans-serif;letter-spacing:-.055em;margin:0 0 16px}.intro{font-size:14px;line-height:1.6;max-width:410px;color:var(--muted);margin:0}.square-mark{width:84px;height:84px;flex:none;color:var(--violet);margin:0 2px 4px}.board-layout{display:grid;grid-template-columns:minmax(0,1fr) 284px;gap:28px;padding-top:26px}.topics{display:flex;flex-wrap:wrap;gap:7px;margin:0 0 24px}.topic{appearance:none;display:flex;align-items:center;gap:7px;min-height:38px;padding:8px 10px;border:1px solid var(--line);border-radius:4px;background:transparent;font:11px system-ui,Arial,Helvetica,sans-serif;color:var(--muted);cursor:pointer;transition:background .16s,border-color .16s,color .16s}.topic.selected{background:#112219;border-color:var(--green);color:var(--ink)}.topic:hover{border-color:#666;color:var(--ink);background:#1c1c1c}.topic-dot{width:5px;height:5px;border-radius:50%;flex:none}.topic-count{color:var(--muted);font-size:10px}.board-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 16px}.board-heading h2{font:500 25px system-ui,Arial,Helvetica,sans-serif;letter-spacing:-.025em;margin:0}.newest{color:var(--muted);font-size:10px;white-space:nowrap}.messages{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;align-items:start}.message{background:var(--surface);border:1px solid var(--line);border-radius:4px;padding:20px 18px 15px;min-width:0;overflow-wrap:anywhere}.message-top{display:flex;justify-content:space-between;gap:12px;align-items:center}.message-topic{color:color-mix(in srgb,var(--topic-color) 75%,white);font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.09em}.message-number{font:11px system-ui,Arial,Helvetica,sans-serif;color:var(--muted);font-variant-numeric:tabular-nums}.message-body{font:16px/1.6 system-ui,Arial,Helvetica,sans-serif;white-space:pre-wrap;margin:22px 0 24px;overflow-wrap:anywhere}.message footer{border-top:1px solid var(--line);padding-top:13px;display:flex;justify-content:space-between;gap:8px;align-items:center}.author{font-size:11px;display:flex;align-items:center;gap:6px;min-width:0;flex-wrap:wrap}.author-initial{display:inline-grid;place-items:center;width:24px;height:24px;border:1px solid #615076;background:#241a32;color:#d9c4f8;border-radius:50%;flex:none}.you{font-size:10px;color:var(--muted)}.remove-message{border:0;background:transparent;font:11px system-ui,Arial,Helvetica,sans-serif;color:var(--muted);padding:7px 5px;cursor:pointer}.remove-message:hover{color:#ff8549}.compose{border:1px solid var(--line);border-top:2px solid var(--violet);border-radius:4px;background:var(--surface);padding:22px;height:fit-content}.compose h2{font:500 28px system-ui,Arial,Helvetica,sans-serif;letter-spacing:-.04em;margin:0 0 8px}.compose-intro{font-size:12px;line-height:1.6;color:var(--muted);margin:0 0 22px}.compose label{display:block;font-size:11px;margin:16px 0 8px}.compose select,.compose textarea{display:block;box-sizing:border-box;width:100%;border:1px solid #444;border-radius:3px;background:#080808;padding:11px;color:var(--ink);font:12px/1.5 system-ui,Arial,Helvetica,sans-serif}.compose textarea{min-height:145px;resize:vertical}.compose textarea::placeholder{color:var(--muted)}.post-button{display:flex;justify-content:space-between;align-items:center;width:100%;min-height:44px;margin-top:13px;border:1px solid var(--green);border-radius:3px;padding:13px;background:var(--green);color:#000;font:500 12px system-ui,Arial,Helvetica,sans-serif;cursor:pointer;transition:background .16s}.post-button:hover{background:#57dc8c}.public-note{font-size:10px;line-height:1.5;color:var(--muted);margin:14px 0 0}.empty-board{grid-column:1/-1;border:1px dashed #444;border-radius:4px;padding:40px 26px;text-align:center;min-height:230px;display:grid;place-content:center;background:var(--surface)}.empty-board h3{font:500 28px system-ui,Arial,Helvetica,sans-serif;letter-spacing:-.03em;margin:0 0 12px}.empty-board p{font:12px/1.8 system-ui,Arial,Helvetica,sans-serif;color:var(--muted);margin:0;max-width:330px}.board-note{display:flex;gap:9px;align-items:center;margin:24px 0 0;font-size:10px;color:var(--muted)}.note-dot{width:6px;height:6px;border-radius:50%;background:var(--green)}.square button:focus-visible,.square select:focus-visible,.square textarea:focus-visible{outline:2px solid #b58cff;outline-offset:3px}
    @media(max-width:820px){.square{padding:32px 24px}.board-layout{grid-template-columns:minmax(0,1fr) 240px;gap:18px}.messages{grid-template-columns:minmax(0,1fr)}.compose{padding:18px}}
    @media(max-width:580px){.square{padding:28px 18px}.board-layout{display:flex;flex-direction:column}.compose{order:-1}.compose textarea{min-height:90px}.square-mark{width:58px;height:58px}.square-header{gap:15px}.topics{gap:6px;margin-bottom:20px}.messages{grid-template-columns:minmax(0,1fr)}.intro{font-size:12px}}
    @media(prefers-reduced-motion:reduce){.topic,.post-button{transition:none}}
  </style><main class="square" data-key="town-square" data-theme="devday"><header class="square-header"><div><p class="eyebrow">Nora / OpenAI DevDay [2026]</p><h1>Town Square.</h1><p class="intro">Good company. Little discoveries.<br>A shared noticeboard, made by everyone who stops by.</p></div><svg class="square-mark" viewBox="0 0 84 84" aria-hidden="true"><rect x="10" y="19" width="54" height="45" rx="4" fill="none" stroke="currentColor" stroke-width="1.5" transform="rotate(-9 37 41)"/><rect x="23" y="12" width="48" height="51" rx="3" fill="#141414" stroke="currentColor" stroke-width="1.5" transform="rotate(7 47 37)"/><circle cx="47" cy="21" r="3" fill="currentColor"/><path d="M33 34h27M33 41h22M33 48h15" stroke="currentColor" stroke-width="1.5"/></svg></header><div class="board-layout"><section aria-label="Shared messages"><nav class="topics" aria-label="Message topics">${pills}</nav><div class="board-heading"><h2>${escape(topic?.label || 'On the board')}</h2><span class="newest">Newest first</span></div><div class="messages" aria-live="polite">${cards || '<div class="empty-board"><h3>The conversation starts here.</h3><p>' + escape(topic?.description || 'Introduce yourself, share an idea, ask a question, or pass on a little discovery.') + '</p></div>'}</div><p class="board-note"><span class="note-dot"></span>A little kindness makes room for everyone.</p></section><aside class="compose"><h2>Leave a note.</h2><p class="compose-intro">A thought worth sharing can start something good.</p><form data-key="compose-${escape(actor.id)}-${ownLast}-${escape(selected)}" data-action="${action({ type: 'post_message' })}" aria-label="Post a message"><label for="message-topic">Topic</label><select id="message-topic" name="topicId">${options}</select><label for="message-body">Your message</label><textarea id="message-body" name="body" maxlength="600" required placeholder="What would you like to share?"></textarea><button type="submit" class="post-button">Post message<span aria-hidden="true">↗</span></button></form><p class="public-note">Posting as ${escape(actor.name)}. Messages are visible to everyone in this world. Up to 600 characters.</p></aside></div></main>`;
}

export function reduce(state, action, actor) {
  const next = JSON.parse(JSON.stringify(state));
  if (action.type === 'select_topic') {
    if (action.topicId !== 'all' && !topicFor(action.topicId)) throw new Error('Choose one of the board topics.');
    next.extras.boardPreferences = { ...next.extras.boardPreferences, [actor.id]: { ...next.extras.boardPreferences?.[actor.id], actorId: actor.id, topicId: action.topicId } };
    return next;
  }
  if (action.type === 'post_message') {
    if (!topicFor(action.topicId)) throw new Error('Choose a topic for your message.');
    if (typeof action.body !== 'string' || !action.body.trim() || action.body.length > 600) throw new Error('Write a message between 1 and 600 characters.');
    const messages = messagesFor(state);
    if (messages.length >= 120) throw new Error('The board is full. Remove one of your earlier messages before posting again.');
    // Keep issued numbers even when notes are deleted. A stale Remove action
    // from another tab must never target a newer note that reuses the same ID.
    const lastIssued = Object.values(state.extras.boardPreferences || {}).reduce((latest, preference) =>
      Math.max(latest, Number.isSafeInteger(preference.lastMessageSequence) ? preference.lastMessageSequence : 0), 0);
    const sequence = messages.reduce((latest, [, message]) => Math.max(latest, message.sequence), lastIssued) + 1;
    if (!Number.isSafeInteger(sequence)) throw new Error('The board cannot accept another message.');
    const id = actor.id + '-' + sequence;
    next.extras.boardMessages = { ...next.extras.boardMessages, [id]: { actorId: actor.id, authorName: actor.name, topicId: action.topicId, body: action.body.trim(), sequence } };
    next.extras.boardPreferences = { ...next.extras.boardPreferences, [actor.id]: { ...next.extras.boardPreferences?.[actor.id], actorId: actor.id, topicId: action.topicId, lastMessageSequence: sequence } };
    // Budget the full board, including escaped text, before accepting a post.
    // A filtered view must never allow an unreadable All topics view to build up.
    const allTopics = { ...next, extras: { ...next.extras, boardPreferences: {} } };
    const otherAuthorControls = messages.filter(([, message]) => message.actorId !== actor.id).length * 512;
    if (render(allTopics, actor).length + otherAuthorControls > 160000) throw new Error('The board is full. Remove one of your earlier messages before posting again.');
    return next;
  }
  if (action.type === 'delete_message') {
    const message = typeof action.messageId === 'string' && state.extras.boardMessages?.[action.messageId];
    if (!message || message.actorId !== actor.id) throw new Error('You can only remove your own messages.');
    delete next.extras.boardMessages[action.messageId];
    return next;
  }
  throw new Error('Choose a topic, post a message, or remove one of your own notes.');
}
