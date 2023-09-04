import { db } from '@/index'
import { onRequest } from 'firebase-functions/v2/https'
import { getUserAuth } from '@/lib'
import { publicHttpOption } from '@/routings/options'
import { AddStreamUserChatRoomMessageParams } from '@/types/http/addStreamUserChatRoomMessageParams'
import { defineSecret } from 'firebase-functions/params'
import {
  UserChatRoom,
  UserChatRoomMessage,
  genUserChatRoomPath,
  genUserChatRoomMessagePath,
} from '@/models'
import { OpenAI, OpenAIMessage } from '@skeet-framework/ai'
import { TypedRequestBody } from '@/types/http'
import { add, get, query, update } from '@skeet-framework/firestore'
import { inspect } from 'util'

const chatGptOrg = defineSecret('CHAT_GPT_ORG')
const chatGptKey = defineSecret('CHAT_GPT_KEY')

export const addStreamUserChatRoomMessage = onRequest(
  { ...publicHttpOption, secrets: [chatGptOrg, chatGptKey] },
  async (req: TypedRequestBody<AddStreamUserChatRoomMessageParams>, res) => {
    const organization = chatGptOrg.value()
    const apiKey = chatGptKey.value()

    try {
      if (!organization || !apiKey)
        throw new Error(
          `ChatGPT organization or apiKey is empty\nPlease run \`skeet add secret CHAT_GPT_ORG/CHAT_GPT_KEY\``,
        )

      // Get Request Body
      const body = {
        userChatRoomId: req.body.userChatRoomId || '',
        content: req.body.content,
      }
      if (body.userChatRoomId === '') throw new Error('userChatRoomId is empty')

      // Get User Info from Firebase Auth
      const user = await getUserAuth(req)

      // Get UserChatRoom
      const chatRoomPath = genUserChatRoomPath(user.uid)
      const userChatRoom = await get<UserChatRoom>(
        db,
        chatRoomPath,
        body.userChatRoomId,
      )

      // Add User Message to UserChatRoomMessage
      const messagesPath = genUserChatRoomMessagePath(
        user.uid,
        body.userChatRoomId,
      )
      await add<UserChatRoomMessage>(db, messagesPath, {
        userChatRoomId: body.userChatRoomId,
        content: body.content,
        role: 'user',
      })

      // Get UserChatRoomMessages for OpenAI Request

      const allMessages = await query<UserChatRoomMessage>(db, messagesPath, [
        {
          field: 'createdAt',
          orderDirection: 'desc',
        },
        {
          limit: 5,
        },
      ])
      allMessages.reverse()

      let promptMessages = allMessages.map((message: UserChatRoomMessage) => {
        return {
          role: message.role,
          content: message.content,
        }
      })
      promptMessages.unshift({
        role: 'system',
        content: userChatRoom.context,
      })
      console.log('promptMessages', promptMessages)
      const messages = {
        messages: promptMessages as OpenAIMessage[],
      }

      console.log('messages.length', messages.messages.length)

      const openAi = new OpenAI({
        organizationKey: organization,
        apiKey,
        model: userChatRoom.model,
        maxTokens: userChatRoom.maxTokens,
        temperature: userChatRoom.temperature,
        n: 1,
        topP: 1,
        stream: true,
      })
      // Update UserChatRoom Title
      if (messages.messages.length === 2) {
        const title = await openAi.generateTitle(body.content)
        await update<UserChatRoom>(db, chatRoomPath, body.userChatRoomId, {
          title,
        })
      }

      // Get OpenAI Stream
      const stream = await openAi.promptStream(messages)
      const messageResults: any[] = []
      for await (const part of stream) {
        const message = String(part.choices[0].delta.content)
        if (message === '' || message === 'undefined') continue
        console.log(inspect(message, false, null, true /* enable colors */))
        res.write(JSON.stringify({ text: message }))
        messageResults.push(message)
      }
      const message = messageResults.join('')
      await add<UserChatRoomMessage>(db, messagesPath, {
        userChatRoomId: body.userChatRoomId,
        content: message,
        role: 'assistant',
      })
      res.end()
    } catch (error) {
      res.status(500).json({ status: 'error', message: String(error) })
    }
  },
)
