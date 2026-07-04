import { Flex, Space, Typography, theme } from 'antd'
import type { AssistantMessagePart, ChatMessage } from '../../../lib/chat'
import AssistantReasoningTrace from './AssistantReasoningTrace'
import AssistantToolTrace from './AssistantToolTrace'
import CopyButton from './CopyButton'
import MarkdownOutput from './MarkdownOutput'

export default function SharedMessageBubble({ message }: { message: ChatMessage }) {
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
          <Flex vertical gap={6}>
            <Typography.Text style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
              {message.content}
            </Typography.Text>
            <Space size={4} style={{ alignSelf: 'flex-end' }}>
              <CopyButton text={message.content} />
            </Space>
          </Flex>
        ) : (
          <Flex vertical gap={8}>
            {assistantParts.map((part) =>
              part.type === 'reasoning' ? (
                <AssistantReasoningTrace key={part.id} content={part.content} />
              ) : part.type === 'output' ? (
                <MarkdownOutput key={part.id} content={part.content} />
              ) : part.type === 'tool' ? (
                <AssistantToolTrace key={part.id} toolCall={part.tool_call} />
              ) : null,
            )}
            <Space size={4}>
              <CopyButton text={message.content} />
            </Space>
          </Flex>
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
