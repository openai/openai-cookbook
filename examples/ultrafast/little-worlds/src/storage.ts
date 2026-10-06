function legacyStorageKey(key: string) {
  return key.replace(/^little-worlds(?=[:.])/, 'living-spaces');
}

/** Move a saved value only after its replacement is safely stored. */
export function readAppStorage(storage: Storage, key: string): string | null {
  const legacyKey = legacyStorageKey(key);
  const current = storage.getItem(key);
  if (current !== null) {
    try { storage.removeItem(legacyKey); } catch { /* Keep the current value usable. */ }
    return current;
  }
  const legacy = storage.getItem(legacyKey);
  if (legacy !== null) {
    try { storage.setItem(key, legacy); storage.removeItem(legacyKey); } catch { /* Preserve the old value when storage is full or blocked. */ }
  }
  return legacy;
}

export function removeAppStorage(storage: Storage, key: string) {
  storage.removeItem(key);
  storage.removeItem(legacyStorageKey(key));
}

export function writeAppStorage(storage: Storage, key: string, value: string) {
  storage.setItem(key, value);
  storage.removeItem(legacyStorageKey(key));
}
