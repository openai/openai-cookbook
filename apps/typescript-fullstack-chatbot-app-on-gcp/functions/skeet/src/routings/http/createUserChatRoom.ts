import { db } from '@/index'
import { onRequest } from 'firebase-functions/v2/https'
import { genUserChatRoomPath, UserChatRoom } from '@/models'
import { add } from '@skeet-framework/firestore'
import { publicHttpOption } from '@/routings/options'
import { CreateUserChatRoomParams } from '@/types/http/createUserChatRoomParams'
import { getUserAuth } from '@/lib'
import { TypedRequestBody } from '@/types/http'

export const createUserChatRoom = onRequest(
  publicHttpOption,
  async (req: TypedRequestBody<CreateUserChatRoomParams>, res) => {
    try {
      const body = {
        model: req.body.model || 'gpt-3.5-turbo',
        systemContent:
          req.body.systemContent ||
          'This is a great chatbot. This Assistant is very kind and helpful.',
        maxTokens: req.body.maxTokens || 256,
        temperature:
          req.body.temperature == 0
            ? 0
            : !req.body.temperature
            ? 1
            : req.body.temperature,
        stream: req.body.stream || true,
      }
      const user = await getUserAuth(req)

      const parentId = user.uid || ''
      const params: UserChatRoom = {
        title: '',
        model: body.model,
        maxTokens: body.maxTokens,
        temperature: body.temperature,
        stream: body.stream,
        context: body.systemContent,
      }
      const userChatRoomPath = genUserChatRoomPath(parentId)
      const userChatRoomDoc = await add<UserChatRoom>(
        db,
        userChatRoomPath,
        params,
      )
      console.log(`created userChatRoom: ${userChatRoomDoc.id}`)
      res.json({ status: 'success', userChatRoomId: userChatRoomDoc.id })
    } catch (error) {
      res.status(500).json({ status: 'error', message: String(error) })
    }
  },
)
