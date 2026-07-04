import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { App } from 'antd'
import { useNavigate, useParams } from 'react-router-dom'
import * as chatApi from '../../../lib/chat'
import type {
  ChatImage,
  ChatMessage,
  ChatModel,
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
  const [models, setModels] = useState<ChatModel[]>([])
  const [modelConfigError, setModelConfigError] = useState<string | null>(null)
  const [selectedModelId, setSelectedModelIdState] = useState<string | null>(null)
  const [selectedVariant, setSelectedVariantState] = useState<string | null>(null)
  const [pendingImageFiles, setPendingImageFiles] = useState<File[]>([])
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
  const selectedModel = useMemo(
    () => models.find((model) => model.id === selectedModelId) ?? null,
    [models, selectedModelId],
  )
  const selectedModelThinkingEntries = useMemo(
    () => Object.entries(selectedModel?.thinking ?? {}),
    [selectedModel],
  )
  const composerDisabledReason = useMemo(() => {
    if (models.length === 0) return '需要配置模型才能开始对话'
    if (!selectedModel) return '请选择模型'
    if (pendingImageFiles.length > 0 && !selectedModel.visual) return '当前模型不支持图片'
    return null
  }, [models.length, pendingImageFiles.length, selectedModel])

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

  const applyModelPreference = useCallback((availableModels: ChatModel[]) => {
    if (availableModels.length === 0) {
      setSelectedModelIdState(null)
      setSelectedVariantState(null)
      return
    }
    const preference = readLatestUse()
    const model = availableModels.find((item) => item.id === preference?.model) ?? availableModels[0]
    const variants = Object.keys(model.thinking)
    const variant = variants.length === 0
      ? null
      : variants.includes(preference?.variant ?? '')
        ? preference?.variant ?? null
        : variants[0]
    setSelectedModelIdState(model.id)
    setSelectedVariantState(variant)
    writeLatestUse(model.id, variant)
  }, [])

  const refreshModels = useCallback(async () => {
    try {
      const result = await chatApi.listChatModels()
      setModels(result.models)
      setModelConfigError(result.last_error)
      applyModelPreference(result.models)
    } catch (error) {
      toast.error(resolveErrorMessage(error))
      setModels([])
    }
  }, [applyModelPreference, toast])

  useEffect(() => {
    void refreshModels()
    const timer = window.setInterval(() => {
      void refreshModels()
    }, 10000)
    return () => window.clearInterval(timer)
  }, [refreshModels])

  const startNewSession = useCallback((options?: { syncUrl?: boolean }) => {
    updateActiveSessionId(null)
    setMessages([])
    setInput('')
    setPendingImageFiles([])
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

  const setSelectedModelId = (modelId: string) => {
    const model = models.find((item) => item.id === modelId)
    if (!model) return
    const variant = Object.keys(model.thinking)[0] ?? null
    setSelectedModelIdState(model.id)
    setSelectedVariantState(variant)
    setPendingImageFiles((current) => (model.visual ? current : []))
    writeLatestUse(model.id, variant)
  }

  const setSelectedVariant = (variant: string | null) => {
    const normalized = variant || null
    setSelectedVariantState(normalized)
    if (selectedModelId) {
      writeLatestUse(selectedModelId, normalized)
    }
  }

  const addPendingImageFiles = (files: File[]) => {
    if (!selectedModel?.visual) {
      toast.error('当前模型不支持图片')
      return
    }
    const accepted = files.filter((file) => ['image/jpeg', 'image/png', 'image/webp'].includes(file.type))
    if (accepted.length !== files.length) {
      toast.warning('仅支持 JPEG、PNG、WebP 图片')
    }
    setPendingImageFiles((current) => [...current, ...accepted].slice(0, 8))
  }

  const removePendingImageFile = (index: number) => {
    setPendingImageFiles((current) => current.filter((_, itemIndex) => itemIndex !== index))
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
      (signal, onEvent) =>
        chatApi.editChatMessage({
          messageId,
          message: prompt,
          model: selectedModel?.id ?? null,
          variant: selectedVariant,
          signal,
          onEvent,
        }),
      () => {
        setEditingMessageId(null)
        setEditingMessageContent('')
        setMessages((current) => ensureStreamingAssistant(current, activeSessionIdRef.current))
      },
    )
  }

  const regenerateLatestMessage = async () => {
    if (!activeSessionId || streaming || !selectedModel) return
    await runStreamingRequest(
      (signal, onEvent) =>
        chatApi.regenerateChatSession({
          sessionId: activeSessionId,
          model: selectedModel.id,
          variant: selectedVariant,
          signal,
          onEvent,
        }),
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
    if ((!prompt && pendingImageFiles.length === 0) || streaming || !selectedModel) return
    if (pendingImageFiles.length > 0 && !selectedModel.visual) {
      toast.error('当前模型不支持图片')
      return
    }
    let uploadedImages: ChatImage[] = []
    try {
      uploadedImages = await Promise.all(pendingImageFiles.map((file) => chatApi.uploadChatImage(file)))
    } catch (error) {
      toast.error(resolveErrorMessage(error))
      return
    }
    const displayContent = buildMessageContent(prompt, uploadedImages)
    await runStreamingRequest(
      (signal, onEvent) =>
        chatApi.streamChatMessage({
          sessionId: activeSessionId,
          message: prompt,
          model: selectedModel.id,
          variant: selectedVariant,
          images: uploadedImages,
          signal,
          onEvent,
        }),
      () => {
        setInput('')
        setPendingImageFiles([])
        setMessages((current) =>
          ensureStreamingAssistant(
            appendPendingUserMessage(current, activeSessionIdRef.current, displayContent),
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
    models, modelConfigError, selectedModelId, selectedVariant,
    selectedModel, selectedModelThinkingEntries, pendingImageFiles,
    composerDisabledReason,
    loadingSessions, loadingMessages, streaming, sharing, shareModalOpen, activeShare,
    editingSessionId, editingTitle, editingMessageId, editingMessageContent,
    mutatingSessionId, transcriptRef, setInput, setEditingTitle,
    setEditingMessageContent, setSelectedModelId, setSelectedVariant,
    addPendingImageFiles, removePendingImageFile,
    startNewSession, loadSession, startEditingSession,
    cancelEditingSession, saveSessionTitle, deleteSession, stopStreaming,
    startEditingMessage, cancelEditingMessage, saveEditedMessage,
    regenerateLatestMessage, activateMessageVersion, sendMessage,
    shareActiveSession, closeShareModal,
  }
}

function readLatestUse(): { model: string; variant: string | null } | null {
  try {
    const raw = window.localStorage.getItem('latest_use')
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed.model !== 'string') return null
    return {
      model: parsed.model,
      variant: typeof parsed.variant === 'string' ? parsed.variant : null,
    }
  } catch {
    return null
  }
}

function writeLatestUse(model: string, variant: string | null): void {
  try {
    window.localStorage.setItem('latest_use', JSON.stringify({ model, variant }))
  } catch {
    // localStorage failures should not block chat.
  }
}

function buildMessageContent(text: string, images: ChatImage[]): string {
  const parts = text ? [text] : []
  parts.push(...images.map((image) => `<|IMAGE|>${image.url}</|IMAGE|>`))
  return parts.join('\n')
}
