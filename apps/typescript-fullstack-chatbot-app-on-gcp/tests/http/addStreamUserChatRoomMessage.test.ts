import { AddStreamUserChatRoomMessageParams } from '@/types/http/skeet/addStreamUserChatRoomMessageParams'
import { CreateUserChatRoomParams } from '@/types/http/skeet/createUserChatRoomParams'
import { postFetch } from '../jest.setup'

let userChatRoomId = ''
describe('addStreamUserChatRoomMessage', () => {
  it('createUserChatRoom', async () => {
    const requestBody: CreateUserChatRoomParams = {
      model: 'gpt-3.5-turbo',
      systemContent:
        'This is a great chatbot. This Assistant is very kind and helpful.',
      maxTokens: 50,
      temperature: 1,
      stream: true,
    }
    const endpoint = '/createUserChatRoom'
    const response = await postFetch<CreateUserChatRoomParams>(
      endpoint,
      requestBody
    )
    const data = await response.json()
    expect(response.status).toEqual(200)
    expect(data).toEqual(
      expect.objectContaining({
        status: 'success',
        userChatRoomRef: expect.any(Object),
        userChatRoomMessageRef: expect.any(Object),
      })
    )
    userChatRoomId = data.userChatRoomRef.id
  })

  it('addStreamUserChatRoomMessage', async () => {
    const requestBody: AddStreamUserChatRoomMessageParams = {
      userChatRoomId,
      content: 'Hello Test!',
      isFirstMessage: true,
    }
    const endpoint = '/addStreamUserChatRoomMessage'
    const response = await postFetch<AddStreamUserChatRoomMessageParams>(
      endpoint,
      requestBody
    )
    const data = await response.json()
    expect(response.status).toEqual(200)
    expect(data).toEqual(
      expect.objectContaining({
        status: 'streaming',
        userChatRoomMessageId: expect.any(String),
      })
    )
  })
})
