import { Empty, Flex, Input, Modal, Spin, Tag, theme } from 'antd'
import type { AssistantMessagePart, ChatMessage, ChatSessionShare } from '../../../lib/chat'
import AssistantReasoningTrace from './AssistantReasoningTrace'
import AssistantToolTrace from './AssistantToolTrace'
import CopyButton from './CopyButton'
import MarkdownOutput from './MarkdownOutput'
import MessageContent from './MessageContent'

export default function ShareSessionModal({
  open,
  loading,
  share,
  messages,
  onClose,
}: {
  open: boolean
  loading: boolean
  share: ChatSessionShare | null
  messages: ChatMessage[]
  onClose: () => void
}) {
  const { token } = theme.useToken()
  const shareUrl = share ? resolveShareUrl(share.share_url) : ''

  return (
    <Modal
      title="分享对话"
      open={open}
      footer={null}
      onCancel={onClose}
      destroyOnClose
    >
      <Flex vertical gap={16}>
        <Flex
          vertical
          gap={8}
          style={{
            maxHeight: 220,
            overflowY: 'auto',
            border: `1px solid ${token.colorBorder}`,
            borderRadius: 8,
            padding: 12,
            background: token.colorFillQuaternary,
          }}
        >
          {messages.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无消息" />
          ) : (
            messages.map((message) => <PreviewMessage key={message.id} message={message} />)
          )}
        </Flex>

        <Spin spinning={loading}>
          <Flex gap={8}>
            <Input value={shareUrl} readOnly placeholder="正在创建分享链接" />
            <CopyButton text={shareUrl} tooltip="复制链接" disabled={!shareUrl || loading} />
          </Flex>
        </Spin>
      </Flex>
    </Modal>
  )
}

function PreviewMessage({ message }: { message: ChatMessage }) {
  const roleLabel = message.role === 'user' ? '用户' : '助手'
  const color = message.role === 'user' ? 'blue' : 'green'
  const assistantParts = message.parts.length > 0 ? message.parts : fallbackAssistantParts(message)

  return (
    <Flex vertical gap={4}>
      <Tag color={color} style={{ width: 'fit-content' }}>
        {roleLabel}
      </Tag>
      <div className="chat-share-preview-markdown">
        {message.role === 'assistant' ? (
          <Flex vertical gap={6}>
            {assistantParts.map((part) =>
              part.type === 'reasoning' ? (
                <AssistantReasoningTrace key={part.id} content={part.content} />
              ) : part.type === 'output' ? (
                <MarkdownOutput key={part.id} content={part.content} />
              ) : part.type === 'tool' ? (
                <AssistantToolTrace key={part.id} toolCall={part.tool_call} />
              ) : null,
            )}
          </Flex>
        ) : (
          <MessageContent content={message.content || ' '} />
        )}
      </div>
    </Flex>
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

function resolveShareUrl(value: string): string {
  if (!value) {
    return ''
  }
  return value.startsWith('/') ? `${window.location.origin}${value}` : value
}
