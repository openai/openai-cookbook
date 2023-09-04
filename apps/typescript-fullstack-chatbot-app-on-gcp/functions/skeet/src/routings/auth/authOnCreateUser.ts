import { db } from '@/index'
import { User, genUserPath } from '@/models'
import { add } from '@skeet-framework/firestore'
import * as functions from 'firebase-functions/v1'
import { authPublicOption } from '@/routings/options'
import { gravatarIconUrl } from '@skeet-framework/utils'
import skeetConfig from '../../../skeetOptions.json'
const region = skeetConfig.region

export const authOnCreateUser = functions
  .runWith(authPublicOption)
  .region(region)
  .auth.user()
  .onCreate(async (user) => {
    try {
      const { uid, email, displayName, photoURL } = user
      const userParams = {
        uid,
        email: email || '',
        username: displayName || email?.split('@')[0] || '',
        iconUrl:
          photoURL == '' || !photoURL
            ? gravatarIconUrl(email ?? 'info@skeet.dev')
            : photoURL,
      }
      const userRef = await add<User>(db, genUserPath(), userParams, uid)
      console.log({ status: 'success', userId: userRef.id })
    } catch (error) {
      console.log({ status: 'error', message: String(error) })
    }
  })
