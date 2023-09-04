import admin from 'firebase-admin'
import { dotenv } from '@skeet-framework/utils'

dotenv.config()
admin.initializeApp()
export const db = admin.firestore()

export {
  authOnCreateUser,
  addStreamUserChatRoomMessage,
  createUserChatRoom,
  addUserChatRoomMessage,
} from '@/routings'
