import { readAppStorage, removeAppStorage, writeAppStorage } from './storage';

export interface VoiceResumeIntent {
  identity: string | null;
  muted: boolean;
  savedAt: number;
}

const key = 'little-worlds:live-resume';
const lifetime = 2 * 60_000;

/** A one-use, same-tab handoff. Never stores audio, captions, or capabilities. */
export function takeVoiceResume(storage?: Storage, now = Date.now()): VoiceResumeIntent | null {
  try {
    const target = storage ?? sessionStorage;
    const raw = readAppStorage(target, key);
    removeAppStorage(target, key);
    if (!raw) return null;
    const value = JSON.parse(raw);
    if (value?.version !== 1 || typeof value.muted !== 'boolean'
      || !(value.identity === null || typeof value.identity === 'string' && value.identity.length > 0 && value.identity.length <= 160)
      || typeof value.savedAt !== 'number' || !Number.isFinite(value.savedAt)
      || now - value.savedAt > lifetime || value.savedAt > now + 1000) return null;
    return { identity: value.identity, muted: value.muted, savedAt: value.savedAt };
  } catch { return null; }
}

export function saveVoiceResume(intent: VoiceResumeIntent | null, storage?: Storage) {
  try {
    const target = storage ?? sessionStorage;
    if (intent) writeAppStorage(target, key, JSON.stringify({ version: 1, identity: intent.identity, muted: intent.muted, savedAt: intent.savedAt }));
    else removeAppStorage(target, key);
  } catch { /* A blocked storage area must not interrupt an active conversation. */ }
}

export async function canResumeVoice(intent: VoiceResumeIntent, identity: string | null, permissions?: Permissions) {
  if (intent.identity !== identity || Date.now() - intent.savedAt > lifetime) return false;
  try {
    // Only restore an existing grant. Unsupported permission queries fall back
    // to a visible Resume button, never a surprise permission prompt.
    const permissionApi = permissions ?? navigator.permissions;
    const granted = (await permissionApi?.query({ name: 'microphone' as PermissionName }))?.state === 'granted';
    return granted && Date.now() - intent.savedAt <= lifetime;
  } catch { return false; }
}
