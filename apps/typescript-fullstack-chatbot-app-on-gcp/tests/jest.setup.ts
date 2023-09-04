import { RequestInit } from 'node-fetch'
import dotenv from 'dotenv'
dotenv.config()

const PROJECT_ID = process.env.PROJECT_ID || ''
const REGION = process.env.REGION || ''

export const BASE_URL = `http://127.0.0.1:5001/${PROJECT_ID}/${REGION}`
const ACCESS_TOKEN = process.env.ACCESS_TOKEN || ''
if (ACCESS_TOKEN === '') {
  console.error(
    'ACCESS_TOKEN is not defined\n Please run `skeet login` to get your access token.'
  )
  process.exit(1)
}

export const postFetch = async <T>(path: string, params: T, isAuth = true) => {
  try {
    const body = JSON.stringify(params)
    const headers: RequestInit['headers'] = isAuth
      ? {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${ACCESS_TOKEN}`,
        }
      : {
          'Content-Type': 'application/json',
        }
    const response = await fetch(`${BASE_URL}${path}`, {
      method: 'POST',
      headers,
      body,
    })
    return response
  } catch (error) {
    throw new Error(`postFetch: ${error}`)
  }
}
