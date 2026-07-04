import type { AssistantMessagePart, ChatMessage, ToolCallTrace } from '../../../lib/chat'
import { PENDING_USER_MESSAGE_ID, STREAMING_MESSAGE_ID } from './constants'

export function appendOrReplaceMessage(
  current: ChatMessage[],
  nextMessage: ChatMessage,
): ChatMessage[] {
  const withoutPendingUser =
    nextMessage.role === 'user'
      ? current.filter((item) => item.id !== PENDING_USER_MESSAGE_ID)
      : current
  const exists = withoutPendingUser.some((item) => item.id === nextMessage.id)
  if (exists) {
    return sortMessages(
      withoutPendingUser.map((item) => (item.id === nextMessage.id ? nextMessage : item)),
    )
  }
  return sortMessages([...withoutPendingUser, nextMessage])
}

export function appendPendingUserMessage(
  current: ChatMessage[],
  activeSessionId: string | null,
  content: string,
): ChatMessage[] {
  const withoutPending = current.filter((item) => item.id !== PENDING_USER_MESSAGE_ID)
  return [
    ...withoutPending,
    {
      id: PENDING_USER_MESSAGE_ID,
      session_id: activeSessionId ?? '',
      role: 'user',
      content,
      parent_message_id: null,
      source_message_id: null,
      version_index: 1,
      version_count: 1,
      version_position: 1,
      previous_version_message_id: null,
      next_version_message_id: null,
      tool_calls: [],
      parts: [],
      sequence: withoutPending.length + 1,
      created_at: new Date().toISOString(),
    },
  ]
}

export function resetMessageBranch(
  current: ChatMessage[],
  parentMessageId: number | null,
): ChatMessage[] {
  const withoutPending = current.filter((item) => item.id !== PENDING_USER_MESSAGE_ID)
  if (parentMessageId === null) {
    return []
  }
  const parentIndex = withoutPending.findIndex((item) => item.id === parentMessageId)
  if (parentIndex < 0) {
    return withoutPending.filter((item) => item.id !== STREAMING_MESSAGE_ID)
  }
  return withoutPending.slice(0, parentIndex + 1)
}

export function appendAssistantDelta(
  current: ChatMessage[],
  activeSessionId: string | null,
  partId: string,
  delta: string,
): ChatMessage[] {
  const streamingMessage = current.find((item) => item.id === STREAMING_MESSAGE_ID)
  if (streamingMessage) {
    return current.map((item) =>
      item.id === STREAMING_MESSAGE_ID
        ? {
            ...item,
            content: item.content + delta,
            parts: appendOutputDelta(item.parts, partId, delta),
          }
        : item,
    )
  }
  return [
    ...current,
    createStreamingAssistant({
      activeSessionId,
      content: delta,
      parts: [{ id: partId, type: 'output', content: delta }],
      sequence: current.length + 1,
    }),
  ]
}

export function appendAssistantReasoningDelta(
  current: ChatMessage[],
  activeSessionId: string | null,
  partId: string,
  delta: string,
): ChatMessage[] {
  const withAssistant = ensureStreamingAssistant(current, activeSessionId)
  return withAssistant.map((item) =>
    item.id === STREAMING_MESSAGE_ID
      ? {
          ...item,
          parts: appendReasoningDelta(item.parts, partId, delta),
        }
      : item,
  )
}

export function upsertAssistantToolCall(
  current: ChatMessage[],
  activeSessionId: string | null,
  toolCall: ToolCallTrace,
): ChatMessage[] {
  const withAssistant = ensureStreamingAssistant(current, activeSessionId)
  return withAssistant.map((item) => {
    if (item.id !== STREAMING_MESSAGE_ID) {
      return item
    }
    return {
      ...item,
      tool_calls: upsertToolCall(item.tool_calls, toolCall),
      parts: upsertToolPart(item.parts, toolCall),
    }
  })
}

export function replaceStreamingMessage(
  current: ChatMessage[],
  finalMessage: ChatMessage,
): ChatMessage[] {
  const withoutStreaming = current.filter((item) => item.id !== STREAMING_MESSAGE_ID)
  const withoutDuplicate = withoutStreaming.filter((item) => item.id !== finalMessage.id)
  return sortMessages([...withoutDuplicate, finalMessage])
}

export function ensureStreamingAssistant(
  current: ChatMessage[],
  activeSessionId: string | null,
): ChatMessage[] {
  if (current.some((item) => item.id === STREAMING_MESSAGE_ID)) {
    return current
  }
  return [
    ...current,
    createStreamingAssistant({
      activeSessionId,
      content: '',
      parts: [],
      sequence: current.length + 1,
    }),
  ]
}

function createStreamingAssistant({
  activeSessionId,
  content,
  parts,
  sequence,
}: {
  activeSessionId: string | null
  content: string
  parts: AssistantMessagePart[]
  sequence: number
}): ChatMessage {
  return {
    id: STREAMING_MESSAGE_ID,
    session_id: activeSessionId ?? '',
    role: 'assistant',
    content,
    parent_message_id: null,
    source_message_id: null,
    version_index: 1,
    version_count: 1,
    version_position: 1,
    previous_version_message_id: null,
    next_version_message_id: null,
    tool_calls: [],
    parts,
    sequence,
    created_at: new Date().toISOString(),
  }
}

function sortMessages(messages: ChatMessage[]): ChatMessage[] {
  return [...messages].sort((a, b) => a.sequence - b.sequence || a.id - b.id)
}

function appendOutputDelta(
  parts: AssistantMessagePart[],
  partId: string,
  delta: string,
): AssistantMessagePart[] {
  const existingPart = parts.find((part) => part.id === partId)
  if (existingPart?.type === 'output') {
    return parts.map((part) =>
      part.id === partId && part.type === 'output'
        ? { ...part, content: `${part.content}${delta}` }
        : part,
    )
  }
  return [...parts, { id: partId, type: 'output', content: delta }]
}

function appendReasoningDelta(
  parts: AssistantMessagePart[],
  partId: string,
  delta: string,
): AssistantMessagePart[] {
  const existingPart = parts.find((part) => part.id === partId)
  if (existingPart?.type === 'reasoning') {
    return parts.map((part) =>
      part.id === partId && part.type === 'reasoning'
        ? { ...part, content: `${part.content}${delta}` }
        : part,
    )
  }
  return [...parts, { id: partId, type: 'reasoning', content: delta }]
}

function upsertToolCall(
  toolCalls: ToolCallTrace[],
  toolCall: ToolCallTrace,
): ToolCallTrace[] {
  const exists = toolCalls.some((item) => item.id === toolCall.id)
  if (exists) {
    return toolCalls.map((item) => (item.id === toolCall.id ? toolCall : item))
  }
  return [...toolCalls, toolCall]
}

function upsertToolPart(
  parts: AssistantMessagePart[],
  toolCall: ToolCallTrace,
): AssistantMessagePart[] {
  const exists = parts.some((part) => part.id === toolCall.id)
  if (exists) {
    return parts.map((part) =>
      part.id === toolCall.id ? { id: toolCall.id, type: 'tool', tool_call: toolCall } : part,
    )
  }
  return [...parts, { id: toolCall.id, type: 'tool', tool_call: toolCall }]
}
