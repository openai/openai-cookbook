import { CreateUserChatRoomParams } from '@/types/http/skeet/createUserChatRoomParams'
import { postFetch } from '../jest.setup'

describe('POST without Bearer Token /createUserChatRoom', () => {
  it('Responds with Auth Error', async () => {
    const requestBody: CreateUserChatRoomParams = {
      maxTokens: 50,
    }
    const endpoint = '/createUserChatRoom'
    const response = await postFetch<CreateUserChatRoomParams>(
      endpoint,
      requestBody,
      false
    )
    const data = await response.json()
    expect(response.status).toEqual(500)

    expect(data.status).toEqual('error')
    expect(data.message).toContain('Error: getUserAuth:')
  })
})

describe('POST with Bearer Token /createUserChatRoom', () => {
  it('Responds with Success', async () => {
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
  })
})
