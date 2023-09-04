import { db } from '@/index'
import { onRequest } from 'firebase-functions/v2/https'
import { add, get, query, update } from '@skeet-framework/firestore'
import { getUserAuth } from '@/lib'
import { OpenAI, OpenAIOptions } from '@skeet-framework/ai'
import { AddUserChatRoomMessageParams } from '@/types/http/addUserChatRoomMessageParams'
import { publicHttpOption } from '@/routings/options'
import {
  genUserChatRoomMessagePath,
  genUserChatRoomPath,
  UserChatRoom,
  UserChatRoomMessage,
} from '@/models'
import { defineSecret } from 'firebase-functions/params'
import { TypedRequestBody } from '@/types/http'

const chatGptOrg = defineSecret('CHAT_GPT_ORG')
const chatGptKey = defineSecret('CHAT_GPT_KEY')

export const addUserChatRoomMessage = onRequest(
  { ...publicHttpOption, secrets: [chatGptOrg, chatGptKey] },
  async (req: TypedRequestBody<AddUserChatRoomMessageParams>, res) => {
    const organization = chatGptOrg.value()
    const apiKey = chatGptKey.value()
    try {
      if (!organization || !apiKey)
        throw new Error('ChatGPT organization or apiKey is empty')
      const body = {
        userChatRoomId: req.body.userChatRoomId ?? '',
        content: req.body.content,
        isFirstMessage: req.body.isFirstMessage ?? false,
      }
      if (body.userChatRoomId === '') throw new Error('userChatRoomId is empty')
      const user = await getUserAuth(req)

      const userChatRoomPath = genUserChatRoomPath(user.uid)
      const userChatRoom = await get<UserChatRoom>(
        db,
        userChatRoomPath,
        body.userChatRoomId,
      )
      if (!userChatRoom) throw new Error('userChatRoom not found')
      if (userChatRoom.stream === true) throw new Error('stream must be false')

      const userChatRoomMessagePath = genUserChatRoomMessagePath(
        user.uid,
        body.userChatRoomId,
      )
      const messageBody = {
        userChatRoomId: body.userChatRoomId,
        role: 'user',
        content: body.content,
      } as UserChatRoomMessage
      await add<UserChatRoomMessage>(db, userChatRoomMessagePath, messageBody)

      const messages = await query<UserChatRoomMessage>(
        db,
        userChatRoomPath,
        [],
      )
      if (messages.length === 0) throw new Error('messages is empty')

      const options: OpenAIOptions = {
        organizationKey: organization,
        apiKey,
        model: userChatRoom.model,
        maxTokens: userChatRoom.maxTokens,
        temperature: userChatRoom.temperature,
        n: 1,
        topP: 1,
      }
      const openAi = new OpenAI(options)

      const content = await openAi.prompt(messages)
      if (!content) throw new Error('openAiResponse not found')

      const messageBody2 = {
        userChatRoomId: body.userChatRoomId,
        role: 'assistant',
        content,
      } as UserChatRoomMessage
      await add<UserChatRoomMessage>(db, userChatRoomMessagePath, messageBody2)
      if (messages.length === 3) {
        const title = await openAi.generateTitle(body.content)
        await update<UserChatRoom>(db, userChatRoomPath, body.userChatRoomId, {
          title,
        })
      }
      res.json({ status: 'success', response: content })
    } catch (error) {
      res.status(500).json({ status: 'error', message: String(error) })
    }
  },
)
