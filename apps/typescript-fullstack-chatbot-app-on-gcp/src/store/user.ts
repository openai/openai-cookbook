import { atom } from 'recoil'

export type UserState = {
  uid: string
  email: string
  username: string
  iconUrl: string
  emailVerified: boolean
}

export const defaultUser = {
  uid: '',
  email: '',
  username: '',
  iconUrl: '',
  emailVerified: false,
}

export const userState = atom<UserState>({
  key: 'userState',
  default: defaultUser,
})
