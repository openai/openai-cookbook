export function runTests(api) {
  const a = { id: 'board-test-a', name: 'Avery' };
  const b = { id: 'board-test-b', name: 'Blair' };
  const base = { ...api.initialState, extras: { ...api.initialState.extras, boardMessages: {}, boardPreferences: {} } };
  const first = api.reduce(base, { type: 'post_message', topicId: 'ideas', body: 'A shared garden', actorId: b.id }, a);
  const firstId = Object.keys(first.extras.boardMessages)[0];
  const second = api.reduce(first, { type: 'post_message', topicId: 'questions', body: 'Who has seeds?' }, b);
  const all = api.reduce(second, { type: 'select_topic', topicId: 'all' }, a);
  const filtered = api.reduce(all, { type: 'select_topic', topicId: 'ideas' }, b);
  let stolen = false;
  try { api.reduce(second, { type: 'delete_message', messageId: firstId }, b); } catch { stolen = true; }
  const removed = api.reduce(second, { type: 'delete_message', messageId: firstId }, a);
  const emptied = api.reduce(first, { type: 'delete_message', messageId: firstId }, a);
  const switched = api.reduce(emptied, { type: 'select_topic', topicId: 'questions' }, a);
  const postedAgain = api.reduce(switched, { type: 'post_message', topicId: 'questions', body: 'A fresh question' }, a);
  const newId = Object.keys(postedAgain.extras.boardMessages)[0];
  let staleDelete = false;
  try { api.reduce(postedAgain, { type: 'delete_message', messageId: firstId }, a); } catch { staleDelete = true; }
  const unsafe = api.reduce(base, { type: 'post_message', topicId: 'introductions', body: '<script>alert("hello")</script>' }, a);
  const unsafeHtml = api.render(unsafe, a);
  const invalid = [
    { type: 'post_message', topicId: 'unknown', body: 'Hello' },
    { type: 'post_message', topicId: 'ideas', body: ' ' },
    { type: 'post_message', topicId: 'ideas', body: 'x'.repeat(601) },
    { type: 'select_topic', topicId: 'unknown' },
    { type: 'unknown' },
  ].every(action => { try { api.reduce(base, action, a); return false; } catch { return true; } });
  return [
    { name: 'Visitors can share messages with trusted authorship', ok: first.extras.boardMessages[firstId].actorId === a.id && first.extras.boardMessages[firstId].authorName === a.name && Object.keys(second.extras.boardMessages).length === 2 },
    { name: 'All topics shows both participants’ messages', ok: api.render(all, a).includes('A shared garden') && api.render(all, a).includes('Who has seeds?') },
    { name: 'Choosing a topic filters only that visitor’s view', ok: filtered.extras.boardPreferences[a.id].topicId === 'all' && !api.render(filtered, b).includes('Who has seeds?') },
    { name: 'Other participants’ messages cannot be deleted', ok: stolen && Object.keys(removed.extras.boardMessages).length === 1 && Object.values(removed.extras.boardMessages)[0].actorId === b.id },
    { name: 'Deleted message IDs are never reused by later posts', ok: staleDelete && newId !== firstId && postedAgain.extras.boardMessages[newId].sequence > first.extras.boardMessages[firstId].sequence },
    { name: 'User content is rendered as escaped text', ok: unsafeHtml.includes('&lt;script&gt;') && !unsafeHtml.includes('<script>') },
    { name: 'Invalid topics and messages are rejected', ok: invalid },
    { name: 'Existing unrelated features remain intact', ok: Object.entries(api.initialState.extras).filter(([key]) => !['boardMessages', 'boardPreferences'].includes(key)).every(([key, value]) => JSON.stringify(second.extras[key]) === JSON.stringify(value)) },
    { name: 'The board exposes native forms and labelled topic controls', ok: api.render(base, a).includes('name="body"') && api.render(base, a).includes('aria-label="Message topics"') },
  ];
}
