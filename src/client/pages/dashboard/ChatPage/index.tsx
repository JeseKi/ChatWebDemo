import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  App,
  Button,
  Empty,
  Flex,
  Input,
  List,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
  theme,
} from 'antd'
import {
  MessageOutlined,
  PlusOutlined,
  SendOutlined,
  StopOutlined,
  ToolOutlined,
} from '@ant-design/icons'
import * as chatApi from '../../../lib/chat'
import type {
  AssistantMessagePart,
  ChatMessage,
  ChatSession,
  ChatStreamEvent,
  ToolCallTrace,
} from '../../../lib/chat'

const STREAMING_MESSAGE_ID = -1

export default function ChatPage() {
  const { message: toast } = App.useApp()
  const { token } = theme.useToken()
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loadingSessions, setLoadingSessions] = useState(false)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const transcriptRef = useRef<HTMLDivElement | null>(null)

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

  const loadSession = useCallback(async (sessionId: string) => {
    setActiveSessionId(sessionId)
    setLoadingMessages(true)
    try {
      const detail = await chatApi.getChatSession(sessionId)
      setMessages(detail.messages)
      upsertSession(detail)
    } catch (error) {
      toast.error(resolveErrorMessage(error))
    } finally {
      setLoadingMessages(false)
    }
  }, [toast, upsertSession])

  const refreshSessions = useCallback(async (options?: { autoloadFirst?: boolean }) => {
    setLoadingSessions(true)
    try {
      const result = await chatApi.listChatSessions()
      setSessions(result)
      if (options?.autoloadFirst && result.length > 0) {
        void loadSession(result[0].id)
      }
    } catch (error) {
      toast.error(resolveErrorMessage(error))
    } finally {
      setLoadingSessions(false)
    }
  }, [loadSession, toast])

  useEffect(() => {
    void refreshSessions({ autoloadFirst: true })
  }, [refreshSessions])

  useEffect(() => {
    transcriptRef.current?.scrollTo({
      top: transcriptRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages])

  const startNewSession = () => {
    setActiveSessionId(null)
    setMessages([])
    setInput('')
  }

  const stopStreaming = () => {
    abortRef.current?.abort()
    abortRef.current = null
    setStreaming(false)
  }

  const sendMessage = async () => {
    const prompt = input.trim()
    if (!prompt || streaming) {
      return
    }

    setInput('')
    setStreaming(true)
    const controller = new AbortController()
    abortRef.current = controller

    try {
      await chatApi.streamChatMessage({
        sessionId: activeSessionId,
        message: prompt,
        signal: controller.signal,
        onEvent: handleStreamEvent,
      })
      await refreshSessions()
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        toast.error(resolveErrorMessage(error))
      }
    } finally {
      abortRef.current = null
      setStreaming(false)
    }
  }

  const handleStreamEvent = (event: ChatStreamEvent) => {
    if (event.type === 'session_ready') {
      setActiveSessionId(event.session.id)
      upsertSession(event.session)
      return
    }
    if (event.type === 'user_message') {
      appendOrReplaceMessage(event.message)
      return
    }
    if (event.type === 'content_delta') {
      appendAssistantDelta(event.part_id, event.delta)
      return
    }
    if (event.type === 'tool_call_started' || event.type === 'tool_call_completed') {
      upsertAssistantToolCall(event.tool_call)
      return
    }
    if (event.type === 'done') {
      replaceStreamingMessage(event.message)
      upsertSession(event.session)
      return
    }
    if (event.type === 'error') {
      toast.error(event.message)
    }
  }

  const appendOrReplaceMessage = (nextMessage: ChatMessage) => {
    setMessages((current) => {
      const exists = current.some((item) => item.id === nextMessage.id)
      if (exists) {
        return current.map((item) => (item.id === nextMessage.id ? nextMessage : item))
      }
      return [...current, nextMessage]
    })
  }

  const appendAssistantDelta = (partId: string, delta: string) => {
    setMessages((current) => {
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
        {
          id: STREAMING_MESSAGE_ID,
          session_id: activeSessionId ?? '',
          role: 'assistant',
          content: delta,
          tool_calls: [],
          parts: [{ id: partId, type: 'output', content: delta }],
          sequence: current.length + 1,
          created_at: new Date().toISOString(),
        },
      ]
    })
  }

  const upsertAssistantToolCall = (toolCall: ToolCallTrace) => {
    setMessages((current) => {
      const withAssistant = ensureStreamingAssistant(current)
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
    })
  }

  const replaceStreamingMessage = (finalMessage: ChatMessage) => {
    setMessages((current) => {
      const withoutStreaming = current.filter((item) => item.id !== STREAMING_MESSAGE_ID)
      const withoutDuplicate = withoutStreaming.filter((item) => item.id !== finalMessage.id)
      return [...withoutDuplicate, finalMessage].sort((a, b) => a.sequence - b.sequence)
    })
  }

  const ensureStreamingAssistant = (current: ChatMessage[]): ChatMessage[] => {
    if (current.some((item) => item.id === STREAMING_MESSAGE_ID)) {
      return current
    }
    return [
      ...current,
      {
        id: STREAMING_MESSAGE_ID,
        session_id: activeSessionId ?? '',
        role: 'assistant',
        content: '',
        tool_calls: [],
        parts: [],
        sequence: current.length + 1,
        created_at: new Date().toISOString(),
      },
    ]
  }

  return (
    <Flex
      gap={16}
      style={{
        height: 'calc(100vh - 154px)',
        minHeight: 560,
      }}
    >
      <Flex
        vertical
        style={{
          width: 280,
          minWidth: 220,
          borderRight: `1px solid ${token.colorBorder}`,
          paddingRight: 12,
        }}
      >
        <Flex align="center" justify="space-between" style={{ marginBottom: 12 }}>
          <Typography.Title level={5} style={{ margin: 0 }}>
            对话
          </Typography.Title>
          <Tooltip title="新对话">
            <Button icon={<PlusOutlined />} onClick={startNewSession} />
          </Tooltip>
        </Flex>
        <Spin spinning={loadingSessions}>
          <List
            dataSource={sessions}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无对话" /> }}
            renderItem={(session) => (
              <List.Item
                onClick={() => void loadSession(session.id)}
                style={{
                  cursor: 'pointer',
                  paddingInline: 8,
                  borderRadius: 6,
                  background: session.id === activeSessionId ? token.colorPrimaryBg : 'transparent',
                }}
              >
                <List.Item.Meta
                  avatar={<MessageOutlined style={{ color: token.colorPrimary }} />}
                  title={<Typography.Text ellipsis>{session.title}</Typography.Text>}
                  description={new Date(session.updated_at).toLocaleString()}
                />
              </List.Item>
            )}
          />
        </Spin>
      </Flex>

      <Flex vertical flex={1} style={{ minWidth: 0 }}>
        <Flex align="center" justify="space-between" style={{ marginBottom: 12 }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            {activeSession?.title ?? '新对话'}
          </Typography.Title>
          {streaming && (
            <Tag color="processing" icon={<Spin size="small" />}>
              生成中
            </Tag>
          )}
        </Flex>

        <div
          ref={transcriptRef}
          style={{
            flex: 1,
            overflowY: 'auto',
            border: `1px solid ${token.colorBorder}`,
            borderRadius: 8,
            padding: 16,
            background: token.colorBgContainer,
          }}
        >
          <Spin spinning={loadingMessages}>
            {messages.length === 0 ? (
              <Empty
                description="发送订单相关问题，例如：查询 ORDER-8831 的状态"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            ) : (
              <Flex vertical gap={12}>
                {messages.map((item) => (
                  <MessageBubble key={item.id} message={item} />
                ))}
              </Flex>
            )}
          </Spin>
        </div>

        <Flex gap={8} style={{ marginTop: 12 }}>
          <Input.TextArea
            value={input}
            disabled={streaming}
            autoSize={{ minRows: 2, maxRows: 5 }}
            placeholder="输入消息"
            onChange={(event) => setInput(event.target.value)}
            onPressEnter={(event) => {
              if (!event.shiftKey) {
                event.preventDefault()
                void sendMessage()
              }
            }}
          />
          {streaming ? (
            <Button danger icon={<StopOutlined />} onClick={stopStreaming}>
              停止
            </Button>
          ) : (
            <Button type="primary" icon={<SendOutlined />} onClick={() => void sendMessage()}>
              发送
            </Button>
          )}
        </Flex>
      </Flex>
    </Flex>
  )
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

function upsertToolCall(toolCalls: ToolCallTrace[], toolCall: ToolCallTrace): ToolCallTrace[] {
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

function MessageBubble({ message }: { message: ChatMessage }) {
  const { token } = theme.useToken()
  const isUser = message.role === 'user'
  const assistantParts = message.parts.length > 0 ? message.parts : fallbackAssistantParts(message)

  return (
    <Flex justify={isUser ? 'flex-end' : 'flex-start'}>
      <div
        style={{
          maxWidth: '78%',
          borderRadius: 8,
          padding: '10px 12px',
          background: isUser ? token.colorPrimaryBg : token.colorFillQuaternary,
          border: `1px solid ${isUser ? token.colorPrimaryBorder : token.colorBorderSecondary}`,
        }}
      >
        {isUser ? (
          <Typography.Text
            style={{
              whiteSpace: 'pre-wrap',
              overflowWrap: 'anywhere',
            }}
          >
            {message.content}
          </Typography.Text>
        ) : (
          <Flex vertical gap={8}>
            {assistantParts.length === 0 && message.id === STREAMING_MESSAGE_ID ? (
              <Typography.Text> </Typography.Text>
            ) : (
              assistantParts.map((part) =>
                part.type === 'output' ? (
                  <AssistantOutput key={part.id} content={part.content} />
                ) : (
                  <AssistantTool key={part.id} toolCall={part.tool_call} />
                ),
              )
            )}
          </Flex>
        )}
      </div>
    </Flex>
  )
}

function AssistantOutput({ content }: { content: string }) {
  return (
    <div className="chat-markdown">
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  )
}

function AssistantTool({ toolCall }: { toolCall: ToolCallTrace }) {
  const { token } = theme.useToken()
  const color = toolCall.status === 'completed' ? 'success' : 'processing'
  return (
    <div
      style={{
        border: `1px solid ${token.colorBorder}`,
        borderRadius: 6,
        padding: 10,
        background: token.colorBgElevated,
      }}
    >
      <Space size={8} wrap>
        <ToolOutlined />
        <Typography.Text strong>{toolCall.name}</Typography.Text>
        <Tag color={color}>{toolCall.status}</Tag>
      </Space>
      <pre style={preStyle}>{JSON.stringify(toolCall.arguments, null, 2)}</pre>
      {toolCall.status === 'completed' && (
        <pre style={preStyle}>{JSON.stringify(toolCall.result, null, 2)}</pre>
      )}
    </div>
  )
}

function fallbackAssistantParts(message: ChatMessage): AssistantMessagePart[] {
  if (message.role !== 'assistant') {
    return []
  }
  const parts: AssistantMessagePart[] = []
  if (message.content) {
    parts.push({ id: `${message.id}-output`, type: 'output', content: message.content })
  }
  for (const toolCall of message.tool_calls) {
    parts.push({ id: toolCall.id, type: 'tool', tool_call: toolCall })
  }
  return parts
}

function resolveErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return '请求失败'
}

const preStyle: CSSProperties = {
  margin: '8px 0 0',
  whiteSpace: 'pre-wrap',
  overflowWrap: 'anywhere',
  fontSize: 12,
}
