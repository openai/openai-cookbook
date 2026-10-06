import { setSessionToken } from './api';

// Notify older open tabs too; they still hold valid in-memory session state.
const resetChannels = ['little-worlds:demo-reset', 'living-spaces:demo-reset'];

function clearAppStorage(storage: Storage) {
  for (let index = storage.length - 1; index >= 0; index--) {
    const key = storage.key(index);
    if (key && /^(little-worlds|living-spaces)[:.]/.test(key)) storage.removeItem(key);
  }
}

// Reload after the server commits so pending reads, frames, navigation history,
// and identity state cannot repopulate the reset app with an old response.
export function returnToWelcomeAfterReset(broadcast = true) {
  if (broadcast && typeof BroadcastChannel !== 'undefined') {
    for (const name of resetChannels) {
      const channel = new BroadcastChannel(name);
      channel.postMessage('completed');
      channel.close();
    }
  }
  setSessionToken(null);
  try { clearAppStorage(sessionStorage); } catch { /* Storage is optional. */ }
  try { clearAppStorage(localStorage); } catch { /* Storage is optional. */ }
  window.location.replace('/');
}

export function listenForDemoReset() {
  if (typeof BroadcastChannel === 'undefined') return () => {};
  let completed = false;
  const channels = resetChannels.map(name => {
    const channel = new BroadcastChannel(name);
    channel.onmessage = event => {
      if (!completed && event.data === 'completed') {
        completed = true;
        returnToWelcomeAfterReset(false);
      }
    };
    return channel;
  });
  return () => channels.forEach(channel => channel.close());
}
