import { AddUserChatRoomMessageParams } from '@/types/http/skeet/addUserChatRoomMessageParams'
import { CreateUserChatRoomParams } from '@/types/http/skeet/createUserChatRoomParams'
import { postFetch } from '../jest.setup'

let userChatRoomId = ''

describe('POST with Bearer Token /addUserChatRoomMessage', () => {
  it('createUserChatRoom', async () => {
    const requestBody: CreateUserChatRoomParams = {
      model: 'gpt-3.5-turbo',
      systemContent:
        'This is a great chatbot. This Assistant is very kind and helpful.',
      maxTokens: 50,
      temperature: 1,
      stream: false,
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

  it('addUserChatRoomMessage', async () => {
    const requestBody: AddUserChatRoomMessageParams = {
      userChatRoomId,
      content: 'Hello Test!',
      isFirstMessage: true,
    }
    const endpoint = '/addUserChatRoomMessage'
    const response = await postFetch<AddUserChatRoomMessageParams>(
      endpoint,
      requestBody
    )
    const data = await response.json()
    expect(response.status).toEqual(200)
    expect(data).toEqual(
      expect.objectContaining({
        status: 'success',
      })
    )
  })
})
