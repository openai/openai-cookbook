export const PCM16_200MS_CHUNK_BYTES = 4_800 * 2;

export class Pcm16Chunker {
  constructor(chunkBytes) {
    if (!Number.isInteger(chunkBytes) || chunkBytes <= 0) {
      throw new Error("chunkBytes must be a positive integer.");
    }
    this.chunkBytes = chunkBytes;
    this.pending = new Uint8Array(0);
  }

  get pendingBytes() {
    return this.pending.length;
  }

  push(buffer) {
    const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
    const combined = new Uint8Array(this.pending.length + bytes.length);
    combined.set(this.pending, 0);
    combined.set(bytes, this.pending.length);

    const chunks = [];
    let offset = 0;
    while (offset + this.chunkBytes <= combined.length) {
      chunks.push(combined.slice(offset, offset + this.chunkBytes));
      offset += this.chunkBytes;
    }

    this.pending = combined.slice(offset);
    return chunks;
  }

  flush() {
    if (this.pending.length === 0) {
      return null;
    }
    const flushed = this.pending;
    this.pending = new Uint8Array(0);
    return flushed;
  }

  reset() {
    this.pending = new Uint8Array(0);
  }
}
