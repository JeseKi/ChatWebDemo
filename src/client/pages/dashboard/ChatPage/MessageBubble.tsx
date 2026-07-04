import { Button, Flex, Input, Space, Tooltip, Typography, theme } from 'antd'
import {
  CheckOutlined,
  EditOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import type { AssistantMessagePart, ChatMessage } from '../../../lib/chat'
import AssistantToolTrace from './AssistantToolTrace'
import { STREAMING_MESSAGE_ID } from './constants'
import CopyButton from './CopyButton'
import MarkdownOutput from './MarkdownOutput'
import VersionSwitcher from './VersionSwitcher'

export default function MessageBubble({
  message,
  isLatest,
  streaming,
  editingMessageId,
  editingMessageContent,
  onStartEditingMessage,
  onEditingMessageContentChange,
  onCancelEditingMessage,
  onSaveEditedMessage,
  onRegenerateLatestMessage,
  onActivateMessageVersion,
}: {
  message: ChatMessage
  isLatest: boolean
  streaming: boolean
  editingMessageId: number | null
  editingMessageContent: string
  onStartEditingMessage: (message: ChatMessage) => void
  onEditingMessageContentChange: (value: string) => void
  onCancelEditingMessage: () => void
  onSaveEditedMessage: (messageId: number) => Promise<void>
  onRegenerateLatestMessage: () => Promise<void>
  onActivateMessageVersion: (messageId: number, targetMessageId: number) => Promise<void>
}) {
  const { token } = theme.useToken()
  const isUser = message.role === 'user'
  const isEditing = editingMessageId === message.id
  const assistantParts = message.parts.length > 0 ? message.parts : fallbackAssistantParts(message)

  return (
    <Flex justify={isUser ? 'flex-end' : 'flex-start'}>
      <div
        style={{
          width: isUser && isEditing ? '78%' : undefined,
          maxWidth: '78%',
          borderRadius: 8,
          padding: '10px 12px',
          background: isUser ? token.colorPrimaryBg : token.colorFillQuaternary,
          border: `1px solid ${isUser ? token.colorPrimaryBorder : token.colorBorderSecondary}`,
        }}
      >
        {isUser && isEditing ? (
          <UserMessageEditor
            message={message}
            streaming={streaming}
            editingMessageContent={editingMessageContent}
            onEditingMessageContentChange={onEditingMessageContentChange}
            onCancelEditingMessage={onCancelEditingMessage}
            onSaveEditedMessage={onSaveEditedMessage}
          />
        ) : isUser ? (
          <UserMessageView
            message={message}
            streaming={streaming}
            onStartEditingMessage={onStartEditingMessage}
            onActivateMessageVersion={onActivateMessageVersion}
          />
        ) : (
          <AssistantMessageView
            message={message}
            isLatest={isLatest}
            streaming={streaming}
            assistantParts={assistantParts}
            onRegenerateLatestMessage={onRegenerateLatestMessage}
            onActivateMessageVersion={onActivateMessageVersion}
          />
        )}
      </div>
    </Flex>
  )
}

function UserMessageEditor({
  message,
  streaming,
  editingMessageContent,
  onEditingMessageContentChange,
  onCancelEditingMessage,
  onSaveEditedMessage,
}: {
  message: ChatMessage
  streaming: boolean
  editingMessageContent: string
  onEditingMessageContentChange: (value: string) => void
  onCancelEditingMessage: () => void
  onSaveEditedMessage: (messageId: number) => Promise<void>
}) {
  return (
    <Flex vertical gap={8} style={{ width: '100%' }}>
      <Input.TextArea
        value={editingMessageContent}
        autoSize={{ minRows: 2, maxRows: 8 }}
        autoFocus
        style={{ width: '100%' }}
        onChange={(event) => onEditingMessageContentChange(event.target.value)}
        onPressEnter={(event) => {
          if (!event.shiftKey) {
            event.preventDefault()
            void onSaveEditedMessage(message.id)
          }
        }}
      />
      <Space size={4} style={{ alignSelf: 'flex-end' }}>
        <Button size="small" onClick={onCancelEditingMessage}>
          取消
        </Button>
        <Button
          size="small"
          type="primary"
          icon={<CheckOutlined />}
          disabled={!editingMessageContent.trim() || streaming}
          onClick={() => void onSaveEditedMessage(message.id)}
        >
          保存
        </Button>
      </Space>
    </Flex>
  )
}

function UserMessageView({
  message,
  streaming,
  onStartEditingMessage,
  onActivateMessageVersion,
}: {
  message: ChatMessage
  streaming: boolean
  onStartEditingMessage: (message: ChatMessage) => void
  onActivateMessageVersion: (messageId: number, targetMessageId: number) => Promise<void>
}) {
  return (
    <Flex vertical gap={6}>
      <Typography.Text
        style={{
          whiteSpace: 'pre-wrap',
          overflowWrap: 'anywhere',
        }}
      >
        {message.content}
      </Typography.Text>
      <Space size={4} style={{ alignSelf: 'flex-end' }}>
        <VersionSwitcher
          message={message}
          disabled={streaming}
          onActivateMessageVersion={onActivateMessageVersion}
        />
        <CopyButton text={message.content} />
        <Tooltip title="编辑消息">
          <Button
            size="small"
            type="text"
            icon={<EditOutlined />}
            disabled={streaming}
            onClick={() => onStartEditingMessage(message)}
          />
        </Tooltip>
      </Space>
    </Flex>
  )
}

function AssistantMessageView({
  message,
  isLatest,
  streaming,
  assistantParts,
  onRegenerateLatestMessage,
  onActivateMessageVersion,
}: {
  message: ChatMessage
  isLatest: boolean
  streaming: boolean
  assistantParts: AssistantMessagePart[]
  onRegenerateLatestMessage: () => Promise<void>
  onActivateMessageVersion: (messageId: number, targetMessageId: number) => Promise<void>
}) {
  return (
    <Flex vertical gap={8}>
      {assistantParts.length === 0 && message.id === STREAMING_MESSAGE_ID ? (
        <Typography.Text> </Typography.Text>
      ) : (
        assistantParts.map((part) =>
          part.type === 'output' ? (
            <MarkdownOutput key={part.id} content={part.content} />
          ) : (
            <AssistantToolTrace key={part.id} toolCall={part.tool_call} />
          ),
        )
      )}
      {message.id !== STREAMING_MESSAGE_ID && (
        <Space size={4}>
          <VersionSwitcher
            message={message}
            disabled={streaming}
            onActivateMessageVersion={onActivateMessageVersion}
          />
          <CopyButton text={message.content} />
          {isLatest && (
            <Tooltip title="重新生成">
              <Button
                size="small"
                type="text"
                icon={<ReloadOutlined />}
                disabled={streaming}
                onClick={() => void onRegenerateLatestMessage()}
              />
            </Tooltip>
          )}
        </Space>
      )}
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
