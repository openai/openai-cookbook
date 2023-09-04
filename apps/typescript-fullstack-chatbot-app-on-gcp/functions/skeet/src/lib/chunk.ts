import { Readable, ReadableOptions } from 'stream'

const CHUNK_SIZE = 6

export class ChunkedStream extends Readable {
  private data: string
  private position: number

  constructor(data: string, options?: ReadableOptions) {
    super(options)
    this.data = data
    this.position = 0
  }

  _read(size: number) {
    setTimeout(() => {
      const chunk = this.data.slice(this.position, this.position + CHUNK_SIZE)
      this.push(chunk.length > 0 ? chunk : null)
      this.position += CHUNK_SIZE
    }, 50)
  }
}
