import clsx from 'clsx'
import { useTranslation } from 'next-i18next'
import { PaperAirplaneIcon, PlusCircleIcon } from '@heroicons/react/24/outline'
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  KeyboardEvent,
} from 'react'
import { useRecoilValue } from 'recoil'
import { userState } from '@/store/user'
import { createFirestoreDataConverter, db } from '@/lib/firebase'
import {
  collection,
  doc,
  getDoc,
  getDocs,
  orderBy,
  query,
} from 'firebase/firestore'
import { chatContentSchema } from '@/utils/form'
import { fetchSkeetFunctions } from '@/lib/skeet'
import Image from 'next/image'
import { ChatRoom } from './ChatMenu'
import { AddStreamUserChatRoomMessageParams } from '@/types/http/skeet/addStreamUserChatRoomMessageParams'
import { z } from 'zod'
import { useForm, Controller } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { TextDecoder } from 'text-encoding'
import useToastMessage from '@/hooks/useToastMessage'
import { unified } from 'unified'
import remarkParse from 'remark-parse'
import remark2Rehype from 'remark-rehype'
import rehypeHighlight from 'rehype-highlight'
import rehypeStringify from 'rehype-stringify'
import rehypeCodeTitles from 'rehype-code-titles'
import remarkSlug from 'remark-slug'
import remarkGfm from 'remark-gfm'
import remarkDirective from 'remark-directive'
import remarkExternalLinks from 'remark-external-links'
import {
  UserChatRoom,
  genUserChatRoomMessagePath,
  genUserChatRoomPath,
} from '@/types/models'
import { Timestamp } from '@skeet-framework/firestore'

type ChatMessage = {
  id: string
  role: string
  createdAt: Timestamp | undefined
  updatedAt: Timestamp | undefined
  content: string
}

const schema = z.object({
  chatContent: chatContentSchema,
})

type Inputs = z.infer<typeof schema>

type Props = {
  setNewChatModalOpen: (_value: boolean) => void
  currentChatRoomId: string | null
  getChatRooms: () => void
}

export default function ChatBox({
  setNewChatModalOpen,
  currentChatRoomId,
  getChatRooms,
}: Props) {
  const { t } = useTranslation()
  const user = useRecoilValue(userState)
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [chatRoom, setChatRoom] = useState<ChatRoom | null>(null)
  const addToast = useToastMessage()

  const chatContentRef = useRef<HTMLDivElement>(null)
  const scrollToEnd = useCallback(() => {
    if (currentChatRoomId && chatContentRef.current) {
      chatContentRef.current.scrollTop = chatContentRef.current.scrollHeight
    }
  }, [chatContentRef, currentChatRoomId])

  const {
    handleSubmit,
    formState: { errors },
    control,
    reset,
    watch,
  } = useForm<Inputs>({
    resolver: zodResolver(schema),
    defaultValues: {
      chatContent: '',
    },
  })

  const chatContent = watch('chatContent')
  const chatContentLines = useMemo(() => {
    return (chatContent.match(/\n/g) || []).length + 1
  }, [chatContent])

  const [isFirstMessage, setFirstMessage] = useState(true)

  const getChatRoom = useCallback(async () => {
    if (db && user.uid && currentChatRoomId) {
      const docRef = doc(
        db,
        genUserChatRoomPath(user.uid),
        currentChatRoomId
      ).withConverter(createFirestoreDataConverter<UserChatRoom>())
      const docSnap = await getDoc(docRef)
      if (docSnap.exists()) {
        const data = docSnap.data()
        if (data.title !== '') {
          setFirstMessage(false)
        }
        setChatRoom({ id: docSnap.id, ...data } as ChatRoom)
      } else {
        console.log('No such document!')
      }
    }
  }, [currentChatRoomId, user.uid])

  useEffect(() => {
    getChatRoom()
  }, [getChatRoom])

  const [isSending, setSending] = useState(false)

  const getUserChatRoomMessage = useCallback(async () => {
    if (db && user.uid && currentChatRoomId) {
      const q = query(
        collection(db, genUserChatRoomMessagePath(user.uid, currentChatRoomId)),
        orderBy('createdAt', 'asc')
      )
      const querySnapshot = await getDocs(q)
      const messages: ChatMessage[] = []
      for await (const qs of querySnapshot.docs) {
        const data = qs.data()
        const html = await unified()
          .use(remarkParse)
          .use(remarkDirective)
          .use(remarkGfm)
          .use(remarkSlug)
          .use(remarkExternalLinks, {
            target: '_blank',
            rel: ['noopener noreferrer'],
          })
          .use(remark2Rehype)
          .use(rehypeCodeTitles)
          .use(rehypeHighlight)
          .use(rehypeStringify)
          .process(data.content as string)

        messages.push({
          id: qs.id,
          ...data,
          content: html.value,
        } as ChatMessage)
      }

      setChatMessages(messages)
    }
  }, [currentChatRoomId, user.uid])

  useEffect(() => {
    getUserChatRoomMessage()
  }, [getUserChatRoomMessage])

  useEffect(() => {
    if (chatMessages.length > 0) {
      scrollToEnd()
    }
  }, [chatMessages, scrollToEnd])

  const isDisabled = useMemo(() => {
    return isSending || errors.chatContent != null
  }, [isSending, errors.chatContent])

  const onSubmit = useCallback(
    async (data: Inputs) => {
      try {
        setSending(true)
        if (!isDisabled && user.uid && currentChatRoomId) {
          setChatMessages((prev) => {
            return [
              ...prev,
              {
                id: `UserSendingMessage${new Date().toISOString()}`,
                role: 'user',
                createdAt: undefined,
                updatedAt: undefined,
                content: data.chatContent,
              },
              {
                id: `AssistantAnsweringMessage${new Date().toISOString()}`,
                role: 'assistant',
                createdAt: undefined,
                updatedAt: undefined,
                content: '',
              },
            ]
          })
          const res =
            await fetchSkeetFunctions<AddStreamUserChatRoomMessageParams>(
              'skeet',
              'addStreamUserChatRoomMessage',
              {
                userChatRoomId: currentChatRoomId,
                content: data.chatContent,
                isFirstMessage,
              }
            )
          const reader = await res?.body?.getReader()
          const decoder = new TextDecoder('utf-8')

          while (true && reader) {
            const { value, done } = await reader.read()
            if (done) break
            try {
              const dataString = decoder.decode(value)
              if (dataString != 'Stream done') {
                const data = JSON.parse(dataString)
                setChatMessages((prev) => {
                  const chunkSize = data.text.length
                  if (prev[prev.length - 1].content.length === 0) {
                    prev[prev.length - 1].content =
                      prev[prev.length - 1].content + data.text
                  }
                  if (
                    !prev[prev.length - 1].content
                      .slice(chunkSize * -1)
                      .includes(data.text)
                  ) {
                    prev[prev.length - 1].content =
                      prev[prev.length - 1].content + data.text
                  }

                  return [...prev]
                })
              }
            } catch (e) {
              console.log(e)
            }
          }

          if (chatRoom && chatRoom.title == '') {
            await getChatRoom()
            await getChatRooms()
          }
          await getUserChatRoomMessage()
          reset()
          setFirstMessage(false)
        }
      } catch (err) {
        console.error(err)
        if (
          err instanceof Error &&
          (err.message.includes('Firebase ID token has expired.') ||
            err.message.includes('Error: getUserAuth'))
        ) {
          addToast({
            type: 'error',
            title: t('errorTokenExpiredTitle'),
            description: t('errorTokenExpiredBody'),
          })
        } else {
          addToast({
            type: 'error',
            title: t('errorTitle'),
            description: t('errorBody'),
          })
        }
      } finally {
        setSending(false)
      }
    },
    [
      isDisabled,
      t,
      currentChatRoomId,
      user.uid,
      setFirstMessage,
      isFirstMessage,
      chatRoom,
      getChatRoom,
      getUserChatRoomMessage,
      addToast,
      reset,
      getChatRooms,
    ]
  )

  const onKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
        handleSubmit(onSubmit)()
      }
    },
    [handleSubmit, onSubmit]
  )

  return (
    <>
      <div className="content-height-mobile sm:content-height w-full overflow-y-auto pt-4 sm:flex-1 sm:px-4 sm:pt-0">
        {!currentChatRoomId && (
          <div className="flex h-full w-full flex-col items-center justify-center bg-gray-50 dark:bg-gray-800">
            <div className="flex w-full max-w-md flex-col items-center justify-center gap-6 p-4">
              <h2 className="text-2xl font-bold text-gray-700 dark:text-gray-200">
                {t('chat:chatGPTCustom')}
              </h2>
              <button
                onClick={() => {
                  setNewChatModalOpen(true)
                }}
                className={clsx(
                  'flex w-full flex-row items-center justify-center gap-4 bg-gray-900 px-3 py-2 hover:cursor-pointer hover:bg-gray-700 dark:bg-gray-600 dark:hover:bg-gray-400'
                )}
              >
                <PlusCircleIcon className="h-6 w-6 text-white" />
                <span className="text-lg font-bold text-white">
                  {t('chat:newChat')}
                </span>
              </button>
            </div>
          </div>
        )}
        {currentChatRoomId && (
          <div className="flex h-full w-full flex-col justify-between gap-4">
            <div
              ref={chatContentRef}
              className={clsx(
                chatContentLines > 4
                  ? 'chat-height-5'
                  : chatContentLines == 4
                  ? 'chat-height-4'
                  : chatContentLines == 3
                  ? 'chat-height-3'
                  : chatContentLines == 2
                  ? 'chat-height-2'
                  : 'chat-height-1',
                'w-full overflow-y-auto pb-24'
              )}
            >
              <div
                className={clsx('bg-gray-50 dark:bg-gray-800', 'w-full p-4')}
              >
                <div className="mx-auto flex w-full max-w-3xl flex-row items-start justify-center gap-4 p-4 sm:p-6 md:gap-6">
                  {chatRoom?.model === 'gpt-3.5-turbo' && (
                    <Image
                      src={
                        'https://storage.googleapis.com/epics-bucket/BuidlersCollective/Jake.png'
                      }
                      alt="Jake icon"
                      className="my-3 aspect-square h-6 w-6 rounded-full sm:h-10 sm:w-10"
                      unoptimized
                      width={40}
                      height={40}
                    />
                  )}

                  {chatRoom?.model === 'gpt-4' && (
                    <Image
                      src={
                        'https://storage.googleapis.com/epics-bucket/BuidlersCollective/Legend.png'
                      }
                      alt="Legend icon"
                      className="my-3 aspect-square h-6 w-6 rounded-full sm:h-10 sm:w-10"
                      unoptimized
                      width={40}
                      height={40}
                    />
                  )}
                  <div className="flex w-full flex-col">
                    <div className="pb-2">
                      <p className="text-base font-bold text-gray-900 dark:text-white">
                        {chatRoom?.title ? chatRoom?.title : t('noTitle')}
                      </p>
                      <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                        {chatRoom?.model}: {chatRoom?.maxTokens} {t('tokens')}
                      </p>
                    </div>
                    <div className="prose w-full max-w-none dark:prose-invert lg:prose-lg">
                      {chatRoom?.context}
                    </div>
                  </div>
                </div>
              </div>
              {chatMessages.map((chatMessage) => (
                <div
                  key={chatMessage.id}
                  className={clsx(
                    chatMessage.role === 'system' &&
                      'bg-gray-50 dark:bg-gray-800',
                    chatMessage.role === 'assistant' &&
                      'bg-gray-50 dark:bg-gray-800',
                    'w-full p-4'
                  )}
                >
                  <div className="mx-auto flex w-full max-w-3xl flex-row items-start justify-center gap-4 p-4 sm:p-6 md:gap-6">
                    {chatMessage.role === 'user' && (
                      <Image
                        src={user.iconUrl}
                        alt="User icon"
                        className="my-3 aspect-square h-6 w-6 rounded-full sm:h-10 sm:w-10"
                        unoptimized
                        width={40}
                        height={40}
                      />
                    )}
                    {(chatMessage.role === 'assistant' ||
                      chatMessage.role === 'system') &&
                      chatRoom?.model === 'gpt-3.5-turbo' && (
                        <Image
                          src={
                            'https://storage.googleapis.com/epics-bucket/BuidlersCollective/Jake.png'
                          }
                          alt="Jake icon"
                          className="my-3 aspect-square h-6 w-6 rounded-full sm:h-10 sm:w-10"
                          unoptimized
                          width={40}
                          height={40}
                        />
                      )}
                    {(chatMessage.role === 'assistant' ||
                      chatMessage.role === 'system') &&
                      chatRoom?.model === 'gpt-4' && (
                        <Image
                          src={
                            'https://storage.googleapis.com/epics-bucket/BuidlersCollective/Legend.png'
                          }
                          alt="Legend icon"
                          className="my-3 aspect-square h-6 w-6 rounded-full sm:h-10 sm:w-10"
                          unoptimized
                          width={40}
                          height={40}
                        />
                      )}
                    <div className="flex w-full flex-col">
                      {chatMessage.role === 'system' && (
                        <div className="pb-2">
                          <p className="text-base font-bold text-gray-900 dark:text-white">
                            {chatRoom?.title ? chatRoom?.title : t('noTitle')}
                          </p>
                          <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
                            {chatRoom?.model}: {chatRoom?.maxTokens}{' '}
                            {t('tokens')}
                          </p>
                        </div>
                      )}
                      <div className="prose w-full max-w-none dark:prose-invert lg:prose-lg">
                        <div
                          className="w-full max-w-none"
                          dangerouslySetInnerHTML={{
                            __html: chatMessage.content,
                          }}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="flex w-full flex-row items-end gap-4">
              <form onSubmit={handleSubmit(onSubmit)} className="w-full">
                <div className="mx-auto flex w-full max-w-3xl flex-row items-end justify-between gap-4">
                  <Controller
                    name="chatContent"
                    control={control}
                    render={({ field }) => (
                      <textarea
                        {...field}
                        onKeyDown={onKeyDown}
                        className={clsx(
                          chatContentLines > 4
                            ? 'h-48'
                            : chatContentLines == 4
                            ? 'h-36'
                            : chatContentLines == 3
                            ? 'h-28'
                            : chatContentLines == 2
                            ? 'h-20'
                            : `h-10`,
                          'flex-1 border-2 border-gray-900 p-1 font-normal text-gray-900 dark:border-gray-50 dark:bg-gray-800 dark:text-white sm:text-lg'
                        )}
                      />
                    )}
                  />

                  <button
                    type="submit"
                    disabled={isDisabled}
                    className={clsx(
                      'flex h-10 w-10 flex-row items-center justify-center',
                      isDisabled
                        ? 'bg-gray-300 hover:cursor-wait dark:bg-gray-800 dark:text-gray-400'
                        : 'bg-gray-900 hover:cursor-pointer dark:bg-gray-600'
                    )}
                  >
                    <PaperAirplaneIcon className="mx-3 h-6 w-6 flex-shrink-0 text-white" />
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
