import { CloudEvent } from 'firebase-functions/lib/v2/core'
import { MessagePublishedData } from 'firebase-functions/v2/pubsub'

export const parsePubSubMessage = <T>(
  event: CloudEvent<MessagePublishedData<any>>
) => {
  let pubsubMessage = ''
  try {
    pubsubMessage = Buffer.from(event.data.message.data, 'base64').toString(
      'utf-8'
    )
  } catch (err) {
    throw new Error(`Failed to decode pubsub message: ${err}`)
  }

  let pubsubObject: T
  try {
    pubsubObject = JSON.parse(pubsubMessage)
    return pubsubObject
  } catch (err) {
    throw new Error(`Failed to parse pubsub message: ${err}`)
  }
}
