import api, { getApiBaseUrl, refreshAccessToken } from './api'
import { getAccessToken } from './tokenStorage'

export type ChatRole = 'user' | 'assistant'
export type ToolCallStatus = 'running' | 'completed' | 'failed'

export interface ToolCallTrace {
  id: string
  name: string
  display_name?: string | null
  arguments: Record<string, unknown>
  result: unknown
  status: ToolCallStatus
}

export type AssistantMessagePart =
  | {
      id: string
      type: 'reasoning'
      content: string
      tool_call?: null
    }
  | {
      id: string
      type: 'output'
      content: string
      tool_call?: null
    }
  | {
      id: string
      type: 'tool'
      content?: null
      tool_call: ToolCallTrace
    }

export interface ChatMessage {
  id: number
  session_id: string
  role: ChatRole
  content: string
  model_id: string | null
  thinking_effort: string | null
  parent_message_id: number | null
  source_message_id: number | null
  version_index: number
  version_count: number
  version_position: number
  previous_version_message_id: number | null
  next_version_message_id: number | null
  tool_calls: ToolCallTrace[]
  parts: AssistantMessagePart[]
  sequence: number
  created_at: string
}

export type ChatModelIconMode = 'auto' | 'mask' | 'image'

export interface ChatModelIconConfig {
  light?: string | null
  dark?: string | null
  mode?: ChatModelIconMode
}

export type ChatModelIcon = string | ChatModelIconConfig | null

export interface ChatModel {
  provider: string
  id: string
  name: string
  icon: ChatModelIcon
  context: number
  max_output: number
  visual: boolean
  thinking: Record<string, string>
  keep_thinking_content: boolean
}

export interface ChatModelsResponse {
  models: ChatModel[]
  last_error: string | null
}

export interface ChatImage {
  image_id: string
  url: string
  mime_type: string
  width: number
  height: number
}

export interface ChatSession {
  id: string
  title: string
  active_leaf_message_id: number | null
  created_at: string
  updated_at: string
}

export type ChatRunStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled'

export interface ChatRun {
  id: string
  session_id: string
  status: ChatRunStatus
  assistant_message_id: number
  latest_seq: number
  error: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface ChatContextCompression {
  id: number
  session_id: string
  head_end_message_id: number
  tail_start_message_id: number
  source_leaf_message_id: number
  previous_compression_id: number | null
  trigger: string
  summary: string
  summary_model_id: string | null
  original_token_estimate: number
  summary_token_estimate: number
  message_count: number
  applies_to_active_path: boolean
  created_at: string
}

export interface ChatSessionDetail extends ChatSession {
  messages: ChatMessage[]
  active_run: ChatRun | null
  context_compressions: ChatContextCompression[]
}

export interface ChatSessionShare {
  token: string
  share_url: string
  title: string
  message_count: number
  created_at: string
}

export interface SharedChatSession {
  token: string
  title: string
  source_session_id: string
  source_active_leaf_message_id: number | null
  message_count: number
  created_at: string
  messages: ChatMessage[]
}

export type ChatStreamEvent =
  | ({ type: 'session_ready'; session: ChatSession; run?: { id: string } } & ChatStreamEventMeta)
  | ({ type: 'branch_reset'; parent_message_id: number | null; message_id?: number } & ChatStreamEventMeta)
  | ({ type: 'user_message'; message: ChatMessage } & ChatStreamEventMeta)
  | ({ type: 'reasoning_delta'; part_id: string; delta: string } & ChatStreamEventMeta)
  | ({ type: 'content_delta'; part_id: string; delta: string } & ChatStreamEventMeta)
  | ({ type: 'tool_call_started'; tool_call: ToolCallTrace } & ChatStreamEventMeta)
  | ({ type: 'tool_call_completed'; tool_call: ToolCallTrace } & ChatStreamEventMeta)
  | ({ type: 'context_compaction_started'; trigger: string; head_end_message_id: number; tail_start_message_id: number } & ChatStreamEventMeta)
  | ({ type: 'context_compaction_done'; compression: ChatContextCompression } & ChatStreamEventMeta)
  | ({ type: 'context_compaction_warning'; message: string } & ChatStreamEventMeta)
  | ({ type: 'error'; message: string } & ChatStreamEventMeta)
  | ({ type: 'done'; message: ChatMessage; session: ChatSession } & ChatStreamEventMeta)

export interface ChatStreamEventMeta {
  seq?: number
  run_id?: string
}

export async function listChatModels(): Promise<ChatModelsResponse> {
  const { data } = await api.get<ChatModelsResponse>('/chat/models')
  return data
}

export async function uploadChatImage(file: File): Promise<ChatImage> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post<ChatImage>('/chat/images', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function listChatSessions(): Promise<ChatSession[]> {
  const { data } = await api.get<ChatSession[]>('/chat/sessions')
  return data
}

export async function getChatSession(sessionId: string): Promise<ChatSessionDetail> {
  const { data } = await api.get<ChatSessionDetail>(`/chat/sessions/${sessionId}`)
  return data
}

export async function updateChatSessionTitle(
  sessionId: string,
  title: string,
): Promise<ChatSession> {
  const { data } = await api.patch<ChatSession>(`/chat/sessions/${sessionId}`, { title })
  return data
}

export async function deleteChatSession(sessionId: string): Promise<void> {
  await api.delete(`/chat/sessions/${sessionId}`)
}

export async function createChatSessionShare(sessionId: string): Promise<ChatSessionShare> {
  const { data } = await api.post<ChatSessionShare>(`/chat/sessions/${sessionId}/shares`)
  return data
}

export async function getSharedChatSession(token: string): Promise<SharedChatSession> {
  const { data } = await api.get<SharedChatSession>(`/chat/shares/${token}`)
  return data
}

export async function streamChatMessage(params: {
  sessionId?: string | null
  message: string
  model?: string | null
  variant?: string | null
  images?: ChatImage[]
  signal?: AbortSignal
  onEvent: (event: ChatStreamEvent) => void
}): Promise<void> {
  const response = await sendStreamRequest('/chat/stream', {
    session_id: params.sessionId || null,
    message: params.message,
    model: params.model ?? null,
    variant: params.variant ?? null,
    images: (params.images ?? []).map((image) => ({
      image_id: image.image_id,
      url: image.url,
      mime_type: image.mime_type,
      width: image.width,
      height: image.height,
    })),
  }, params, false)
  await consumeEventStream(response, params.onEvent)
}

export async function streamChatRunEvents(params: {
  runId: string
  after?: number
  signal?: AbortSignal
  onEvent: (event: ChatStreamEvent) => void
}): Promise<void> {
  const response = await sendRunStreamRequest(params, false)
  await consumeEventStream(response, params.onEvent)
}

async function sendRunStreamRequest(
  params: {
    runId: string
    after?: number
    signal?: AbortSignal
    onEvent: (event: ChatStreamEvent) => void
  },
  alreadyRetried: boolean,
): Promise<Response> {
  const token = getAccessToken()
  const query = new URLSearchParams({ after: String(params.after ?? 0) })
  const response = await fetch(`${getApiBaseUrl()}/chat/runs/${params.runId}/stream?${query}`, {
    method: 'GET',
    credentials: 'include',
    signal: params.signal,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })

  if (response.status === 401 && !alreadyRetried) {
    const refreshedToken = await refreshAccessToken()
    if (refreshedToken) {
      return sendRunStreamRequest(params, true)
    }
  }

  if (!response.ok || !response.body) {
    const text = await response.text()
    throw new Error(text || `请求失败：${response.status}`)
  }

  return response
}

export async function editChatMessage(params: {
  messageId: number
  message: string
  model?: string | null
  variant?: string | null
  signal?: AbortSignal
  onEvent: (event: ChatStreamEvent) => void
}): Promise<void> {
  const response = await sendStreamRequest(`/chat/messages/${params.messageId}/edit-stream`, {
    message: params.message,
    model: params.model ?? null,
    variant: params.variant ?? null,
  }, params, false)
  await consumeEventStream(response, params.onEvent)
}

export async function regenerateChatSession(params: {
  sessionId: string
  model?: string | null
  variant?: string | null
  signal?: AbortSignal
  onEvent: (event: ChatStreamEvent) => void
}): Promise<void> {
  const response = await sendStreamRequest(
    `/chat/sessions/${params.sessionId}/regenerate-stream`,
    {
      model: params.model ?? null,
      variant: params.variant ?? null,
    },
    params,
    false,
  )
  await consumeEventStream(response, params.onEvent)
}

export async function activateChatMessageVersion(
  messageId: number,
  targetMessageId: number,
): Promise<ChatSessionDetail> {
  const { data } = await api.post<ChatSessionDetail>(
    `/chat/messages/${messageId}/versions/${targetMessageId}/activate`,
  )
  return data
}

async function sendStreamRequest(
  path: string,
  body: Record<string, unknown>,
  params: {
    signal?: AbortSignal
    onEvent: (event: ChatStreamEvent) => void
  },
  alreadyRetried: boolean,
): Promise<Response> {
  const token = getAccessToken()
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: 'POST',
    credentials: 'include',
    signal: params.signal,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  })

  if (response.status === 401 && !alreadyRetried) {
    const refreshedToken = await refreshAccessToken()
    if (refreshedToken) {
      return sendStreamRequest(path, body, params, true)
    }
  }

  if (!response.ok || !response.body) {
    const text = await response.text()
    throw new Error(text || `请求失败：${response.status}`)
  }

  return response
}

async function consumeEventStream(
  response: Response,
  onEvent: (event: ChatStreamEvent) => void,
): Promise<void> {
  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('浏览器不支持读取流式响应')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) {
      break
    }
    buffer += decoder.decode(value, { stream: true })
    buffer = flushBufferedEvents(buffer, onEvent)
  }

  buffer += decoder.decode()
  flushBufferedEvents(`${buffer}\n\n`, onEvent)
}

function flushBufferedEvents(
  buffer: string,
  onEvent: (event: ChatStreamEvent) => void,
): string {
  const parts = buffer.split('\n\n')
  const pending = parts.pop() ?? ''
  for (const part of parts) {
    const event = parseSseEvent(part)
    if (event) {
      onEvent(event)
    }
  }
  return pending
}

function parseSseEvent(block: string): ChatStreamEvent | null {
  const lines = block.split('\n')
  const eventLine = lines.find((line) => line.startsWith('event:'))
  const dataLines = lines.filter((line) => line.startsWith('data:'))
  if (!eventLine || dataLines.length === 0) {
    return null
  }
  const type = eventLine.slice('event:'.length).trim()
  const data = JSON.parse(dataLines.map((line) => line.slice('data:'.length).trim()).join('\n'))
  return { type, ...data } as ChatStreamEvent
}
