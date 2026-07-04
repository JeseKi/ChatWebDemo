import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { App } from 'antd'
import { useNavigate, useParams } from 'react-router-dom'
import * as chatApi from '../../../lib/chat'
import type {
  ChatMessage,
  ChatSession,
  ChatSessionShare,
  ChatStreamEvent,
} from '../../../lib/chat'
import {
  appendAssistantDelta,
  appendAssistantReasoningDelta,
  appendOrReplaceMessage,
  appendPendingUserMessage,
  ensureStreamingAssistant,
  replaceStreamingMessage,
  resetMessageBranch,
  upsertAssistantToolCall,
} from './messageState'
import { resolveErrorMessage } from './utils'

export function useChatPageController() {
  const { message: toast } = App.useApp()
  const navigate = useNavigate()
  const { sessionId: routeSessionId } = useParams<{ sessionId?: string }>()
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loadingSessions, setLoadingSessions] = useState(false)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [sharing, setSharing] = useState(false)
  const [shareModalOpen, setShareModalOpen] = useState(false)
  const [activeShare, setActiveShare] = useState<ChatSessionShare | null>(null)
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState('')
  const [editingMessageId, setEditingMessageId] = useState<number | null>(null)
  const [editingMessageContent, setEditingMessageContent] = useState('')
  const [mutatingSessionId, setMutatingSessionId] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const activeSessionIdRef = useRef<string | null>(null)
  const transcriptRef = useRef<HTMLDivElement | null>(null)

  const updateActiveSessionId = useCallback((sessionId: string | null) => {
    activeSessionIdRef.current = sessionId
    setActiveSessionId(sessionId)
  }, [])

  const activeSession = useMemo(
    () => sessions.find((session) => session.id === activeSessionId) ?? null,
    [activeSessionId, sessions],
  )

  const upsertSession = useCallback((session: ChatSession) => {
    setSessions((current) => {
      const next = current.filter((item) => item.id !== session.id)
      return [session, ...next].sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    })
  }, [])

  const loadSession = useCallback(async (
    sessionId: string,
    options?: { replace?: boolean; syncUrl?: boolean },
  ) => {
    updateActiveSessionId(sessionId)
    if (options?.syncUrl !== false) {
      navigate(`/chat/${sessionId}`, { replace: options?.replace ?? false })
    }
    setLoadingMessages(true)
    try {
      const detail = await chatApi.getChatSession(sessionId)
      setMessages(detail.messages)
      upsertSession(detail)
    } catch (error) {
      toast.error(resolveErrorMessage(error))
      updateActiveSessionId(null)
      setMessages([])
      navigate('/chat', { replace: true })
    } finally {
      setLoadingMessages(false)
    }
  }, [navigate, toast, updateActiveSessionId, upsertSession])

  const refreshSessions = useCallback(async () => {
    setLoadingSessions(true)
    try {
      const result = await chatApi.listChatSessions()
      setSessions(result)
    } catch (error) {
      toast.error(resolveErrorMessage(error))
    } finally {
      setLoadingSessions(false)
    }
  }, [toast])

  useEffect(() => {
    void refreshSessions()
  }, [refreshSessions])

  const startNewSession = useCallback((options?: { syncUrl?: boolean }) => {
    updateActiveSessionId(null)
    setMessages([])
    setInput('')
    setEditingSessionId(null)
    setEditingTitle('')
    setEditingMessageId(null)
    setEditingMessageContent('')
    if (options?.syncUrl !== false) {
      navigate('/chat')
    }
  }, [navigate, updateActiveSessionId])

  useEffect(() => {
    if (routeSessionId) {
      if (routeSessionId !== activeSessionIdRef.current) {
        void loadSession(routeSessionId, { syncUrl: false })
      }
      return
    }
    startNewSession({ syncUrl: false })
  }, [loadSession, routeSessionId, startNewSession])

  useEffect(() => {
    transcriptRef.current?.scrollTo({
      top: transcriptRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages])

  const startEditingSession = (session: ChatSession) => {
    setEditingSessionId(session.id)
    setEditingTitle(session.title)
  }

  const cancelEditingSession = () => {
    setEditingSessionId(null)
    setEditingTitle('')
  }

  const saveSessionTitle = async (sessionId: string) => {
    const title = editingTitle.trim()
    if (!title) {
      toast.error('会话名称不能为空')
      return
    }
    setMutatingSessionId(sessionId)
    try {
      const updated = await chatApi.updateChatSessionTitle(sessionId, title)
      upsertSession(updated)
      setEditingSessionId(null)
      setEditingTitle('')
      toast.success('会话名称已更新')
    } catch (error) {
      toast.error(resolveErrorMessage(error))
    } finally {
      setMutatingSessionId(null)
    }
  }

  const deleteSession = async (sessionId: string) => {
    setMutatingSessionId(sessionId)
    try {
      await chatApi.deleteChatSession(sessionId)
      let nextActiveSessionId: string | null = null
      setSessions((current) => {
        const next = current.filter((session) => session.id !== sessionId)
        nextActiveSessionId = next[0]?.id ?? null
        return next
      })
      if (activeSessionId === sessionId && nextActiveSessionId) await loadSession(nextActiveSessionId)
      if (activeSessionId === sessionId && !nextActiveSessionId) {
        startNewSession()
      }
      if (editingSessionId === sessionId) cancelEditingSession()
      toast.success('会话已删除')
    } catch (error) {
      toast.error(resolveErrorMessage(error))
    } finally {
      setMutatingSessionId(null)
    }
  }

  const stopStreaming = () => {
    abortRef.current?.abort()
    abortRef.current = null
    setStreaming(false)
  }

  const startEditingMessage = (message: ChatMessage) => {
    setEditingMessageId(message.id)
    setEditingMessageContent(message.content)
  }

  const cancelEditingMessage = () => {
    setEditingMessageId(null)
    setEditingMessageContent('')
  }

  const handleStreamEvent = (event: ChatStreamEvent) => {
    if (event.type === 'session_ready') {
      updateActiveSessionId(event.session.id)
      upsertSession(event.session)
      navigate(`/chat/${event.session.id}`, { replace: true })
      return
    }
    if (event.type === 'branch_reset') {
      setMessages((current) =>
        ensureStreamingAssistant(
          resetMessageBranch(current, event.parent_message_id),
          activeSessionIdRef.current,
        ),
      )
      return
    }
    if (event.type === 'user_message') {
      setMessages((current) => appendOrReplaceMessage(current, event.message))
      return
    }
    if (event.type === 'content_delta') {
      setMessages((current) =>
        appendAssistantDelta(current, activeSessionIdRef.current, event.part_id, event.delta),
      )
      return
    }
    if (event.type === 'reasoning_delta') {
      setMessages((current) =>
        appendAssistantReasoningDelta(
          current,
          activeSessionIdRef.current,
          event.part_id,
          event.delta,
        ),
      )
      return
    }
    if (event.type === 'tool_call_started' || event.type === 'tool_call_completed') {
      setMessages((current) =>
        upsertAssistantToolCall(current, activeSessionIdRef.current, event.tool_call),
      )
      return
    }
    if (event.type === 'done') {
      setMessages((current) => replaceStreamingMessage(current, event.message))
      upsertSession(event.session)
      return
    }
    if (event.type === 'error') toast.error(event.message)
  }

  const runStreamingRequest = async (
    request: (signal: AbortSignal, onEvent: (event: ChatStreamEvent) => void) => Promise<void>,
    beforeStart?: () => void,
  ) => {
    setStreaming(true)
    beforeStart?.()
    const controller = new AbortController()
    abortRef.current = controller
    try {
      await request(controller.signal, handleStreamEvent)
      await refreshSessions()
    } catch (error) {
      if ((error as Error).name !== 'AbortError') toast.error(resolveErrorMessage(error))
    } finally {
      abortRef.current = null
      setStreaming(false)
    }
  }

  const saveEditedMessage = async (messageId: number) => {
    const prompt = editingMessageContent.trim()
    if (!prompt || streaming) return
    await runStreamingRequest(
      (signal, onEvent) => chatApi.editChatMessage({ messageId, message: prompt, signal, onEvent }),
      () => {
        setEditingMessageId(null)
        setEditingMessageContent('')
        setMessages((current) => ensureStreamingAssistant(current, activeSessionIdRef.current))
      },
    )
  }

  const regenerateLatestMessage = async () => {
    if (!activeSessionId || streaming) return
    await runStreamingRequest(
      (signal, onEvent) =>
        chatApi.regenerateChatSession({ sessionId: activeSessionId, signal, onEvent }),
      () => setMessages((current) => ensureStreamingAssistant(current, activeSessionIdRef.current)),
    )
  }

  const activateMessageVersion = async (messageId: number, targetMessageId: number) => {
    if (streaming) return
    setLoadingMessages(true)
    try {
      const detail = await chatApi.activateChatMessageVersion(messageId, targetMessageId)
      updateActiveSessionId(detail.id)
      setMessages(detail.messages)
      upsertSession(detail)
      navigate(`/chat/${detail.id}`, { replace: true })
    } catch (error) {
      toast.error(resolveErrorMessage(error))
    } finally {
      setLoadingMessages(false)
    }
  }

  const sendMessage = async () => {
    const prompt = input.trim()
    if (!prompt || streaming) return
    await runStreamingRequest(
      (signal, onEvent) =>
        chatApi.streamChatMessage({ sessionId: activeSessionId, message: prompt, signal, onEvent }),
      () => {
        setInput('')
        setMessages((current) =>
          ensureStreamingAssistant(
            appendPendingUserMessage(current, activeSessionIdRef.current, prompt),
            activeSessionIdRef.current,
          ),
        )
      },
    )
  }

  const shareActiveSession = async () => {
    if (!activeSessionId || streaming || loadingMessages || sharing) return
    setShareModalOpen(true)
    setActiveShare(null)
    setSharing(true)
    try {
      const share = await chatApi.createChatSessionShare(activeSessionId)
      setActiveShare(share)
    } catch (error) {
      toast.error(resolveErrorMessage(error))
    } finally {
      setSharing(false)
    }
  }

  const closeShareModal = () => {
    setShareModalOpen(false)
  }

  return {
    sessions, activeSessionId, activeSession, messages, input,
    loadingSessions, loadingMessages, streaming, sharing, shareModalOpen, activeShare,
    editingSessionId, editingTitle, editingMessageId, editingMessageContent,
    mutatingSessionId, transcriptRef, setInput, setEditingTitle,
    setEditingMessageContent, startNewSession, loadSession, startEditingSession,
    cancelEditingSession, saveSessionTitle, deleteSession, stopStreaming,
    startEditingMessage, cancelEditingMessage, saveEditedMessage,
    regenerateLatestMessage, activateMessageVersion, sendMessage,
    shareActiveSession, closeShareModal,
  }
}
