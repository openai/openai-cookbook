import { hash } from './store.mjs';

const PART_BYTES = 200_000;
const ITEM_DOCUMENT_BYTES = 300_000;
const validHash = value => /^[a-f0-9]{64}$/.test(value ?? '');

// A linked manifest stays small even when the complete approved enrollment is large.
export function encodeControl(config, enrollment) {
  const bytes = Buffer.from(JSON.stringify({ config, enrollment }));
  const parts = [];
  let next = null;
  const count = Math.ceil(bytes.length / PART_BYTES);
  for (let index = count - 1; index >= 0; index--) {
    const document = JSON.stringify({ version: 1, index, next,
      data: bytes.subarray(index * PART_BYTES, (index + 1) * PART_BYTES).toString('base64') });
    if (Buffer.byteLength(document) > ITEM_DOCUMENT_BYTES) throw new Error('CONTROL_PART_TOO_LARGE');
    next = hash(document);
    parts.push({ index, hash: next, document });
  }
  const document = JSON.stringify({ version: 2, first: next, parts: count,
    bytes: bytes.length, dataSha256: hash(bytes), members: enrollment.members.length });
  return { document, hash: hash(document), parts: parts.reverse() };
}

export function createControlLoader({ store, controlSha256 }) {
  let cached;
  return async () => {
    if (!cached) cached = (async () => {
      const document = await store.getControl();
      if (typeof document !== 'string' || Buffer.byteLength(document) > ITEM_DOCUMENT_BYTES ||
          !validHash(controlSha256) || hash(document) !== controlSha256) throw new Error('CONTROL_HASH_MISMATCH');
      const manifest = JSON.parse(document);
      if (manifest.version !== 2 || !validHash(manifest.first) || !validHash(manifest.dataSha256) ||
          ![manifest.parts, manifest.bytes, manifest.members].every(value => Number.isSafeInteger(value) && value > 0)) {
        throw new Error('CONTROL_MANIFEST_INVALID');
      }
      const buffers = [];
      let next = manifest.first;
      let byteLength = 0;
      for (let index = 0; index < manifest.parts; index++) {
        if (!validHash(next)) throw new Error('CONTROL_CHAIN_INVALID');
        const partText = await store.getControlPart(next);
        if (typeof partText !== 'string' || Buffer.byteLength(partText) > ITEM_DOCUMENT_BYTES || hash(partText) !== next) {
          throw new Error('CONTROL_PART_HASH_MISMATCH');
        }
        const part = JSON.parse(partText);
        if (part.version !== 1 || part.index !== index || typeof part.data !== 'string') throw new Error('CONTROL_PART_INVALID');
        const bytes = Buffer.from(part.data, 'base64');
        if (bytes.toString('base64') !== part.data || !bytes.length || bytes.length > PART_BYTES) throw new Error('CONTROL_PART_INVALID');
        byteLength += bytes.length;
        if (byteLength > manifest.bytes) throw new Error('CONTROL_SIZE_MISMATCH');
        buffers.push(bytes);
        next = part.next;
      }
      const bytes = Buffer.concat(buffers);
      if (next !== null || bytes.length !== manifest.bytes || hash(bytes) !== manifest.dataSha256) throw new Error('CONTROL_SIZE_MISMATCH');
      const control = JSON.parse(bytes.toString('utf8'));
      if (!Array.isArray(control.enrollment?.members) || control.enrollment.members.length !== manifest.members) throw new Error('CONTROL_MEMBER_COUNT_MISMATCH');
      return control;
    })().catch(error => { cached = undefined; throw error; });
    return cached;
  };
}
