import { ChunkedStream } from '@/lib/chunk'
import { Response } from 'firebase-functions/v1'

export const streamResponse = async (response: string, res: Response) => {
  const stream = new ChunkedStream(response)

  stream.on('data', async (chunk) => {
    if (!res.headersSent) {
      res.setHeader('Content-Type', 'application/json')
    }
    console.log(`chunk: ${chunk}`)
    await res.write(JSON.stringify({ text: chunk.toString() }))
  })

  stream.on('end', async () => {
    res.end('Stream done')
  })

  stream.on('error', async (e: Error) => {
    console.error(e)
    if (!res.headersSent) {
      res.status(500).send('Stream error')
    } else {
      res.end()
    }
  })
}
