// end() can precede the socket's close event by an arbitrarily long drain.
// Release producers immediately, before ending the HTTP response.
export function createEventStreamLifecycle(response, principal) {
  let closed = false;
  let heartbeat;
  const cleanups = new Set();
  const cleanup = () => {
    if (closed) return;
    closed = true;
    clearInterval(heartbeat);
    principal.signal.removeEventListener('abort', end);
    response.off('finish', cleanup);
    response.off('close', cleanup);
    for (const dispose of cleanups) dispose();
    cleanups.clear();
  };
  const end = () => {
    cleanup();
    if (!response.destroyed && !response.writableEnded) response.end();
  };
  const writable = () => {
    if (closed) return false;
    if (response.destroyed || response.writableEnded || !principal.active()) {
      end();
      return false;
    }
    return true;
  };
  response.once('finish', cleanup);
  response.once('close', cleanup);
  // Retain this handler for any asynchronous error from an in-flight write,
  // including one delivered after producers have already been released.
  response.on('error', () => {
    cleanup();
    if (!response.destroyed) response.destroy();
  });
  principal.signal.addEventListener('abort', end, { once: true });
  if (principal.signal.aborted) end();
  return {
    end,
    writable,
    onCleanup(dispose) {
      // A feed can synchronously call end() from subscribe() when closed.
      if (closed) dispose();
      else cleanups.add(dispose);
    },
    startHeartbeat(send) {
      if (!writable()) return;
      clearInterval(heartbeat);
      heartbeat = setInterval(() => { if (writable()) send(); }, 15_000);
      heartbeat.unref();
    },
  };
}
