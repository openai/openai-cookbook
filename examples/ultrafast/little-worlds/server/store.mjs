import { mkdir, readFile, writeFile, rename, unlink } from 'node:fs/promises';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';

export const clone = (value) => structuredClone(value);

export function addEvent(data, event) {
  const entry = { id: String(++data.sequence), time: new Date().toISOString(), ...event };
  data.events.push(entry);
  data.events = data.events.slice(-150);
  return entry;
}

// Every state/revision/event mutation goes through one serializable transaction.
// An atomic rename is the commit point. A guard may still veto it after disk I/O.
export async function openStore(directory, initialize) {
  await mkdir(directory, { recursive: true, mode: 0o700 });
  const filename = join(directory, 'space.json');
  let data;
  try {
    data = JSON.parse(await readFile(filename, 'utf8'));
    if (data.version !== 1 || !Array.isArray(data.revisions) || !data.session) {
      throw new Error('The saved space has an unsupported format. Move .local aside to start a new space.');
    }
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
    data = await initialize();
    await writeFile(filename, JSON.stringify(data), { mode: 0o600 });
  }
  let queue = Promise.resolve();
  const listeners = new Set();
  const store = {
    read: () => clone(data),
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    transact(update, guard) {
      const operation = queue.then(async () => {
        const draft = clone(data);
        const previousSequence = data.sequence;
        const result = await update(draft);
        const temporary = join(directory, `.space-${randomUUID()}.tmp`);
        try {
          await writeFile(temporary, JSON.stringify(draft), { mode: 0o600 });
          guard?.();
          await rename(temporary, filename);
          data = draft;
        } catch (error) {
          await unlink(temporary).catch(() => {});
          throw error;
        }
        for (const event of data.events.filter((entry) => Number(entry.id) > previousSequence)) {
          for (const listener of listeners) {
            try { listener(clone(event)); } catch { /* A disconnected viewer cannot abort a commit. */ }
          }
        }
        return clone(result);
      });
      queue = operation.catch(() => {});
      return operation;
    },
    emit(event, guard) { return store.transact((draft) => addEvent(draft, event), guard); },
    flush: () => queue,
  };
  return store;
}
