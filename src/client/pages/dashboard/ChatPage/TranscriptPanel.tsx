import type { RefObject } from 'react'
import { Empty, Flex, Skeleton, theme } from 'antd'
import type { ChatMessage } from '../../../lib/chat'
import MessageBubble from './MessageBubble'

export default function TranscriptPanel({
  transcriptRef,
  messages,
  loadingMessages,
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
  transcriptRef: RefObject<HTMLDivElement | null>
  messages: ChatMessage[]
  loadingMessages: boolean
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

  return (
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
      {loadingMessages ? (
        <TranscriptLoadingPlaceholders />
      ) : messages.length === 0 ? (
        <Empty
          description="发送订单相关问题，例如：查询 ORDER-8831 的状态"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      ) : (
        <Flex vertical gap={12}>
          {messages.map((item) => (
            <MessageBubble
              key={item.id}
              message={item}
              isLatest={item.id === messages[messages.length - 1]?.id}
              streaming={streaming}
              editingMessageId={editingMessageId}
              editingMessageContent={editingMessageContent}
              onStartEditingMessage={onStartEditingMessage}
              onEditingMessageContentChange={onEditingMessageContentChange}
              onCancelEditingMessage={onCancelEditingMessage}
              onSaveEditedMessage={onSaveEditedMessage}
              onRegenerateLatestMessage={onRegenerateLatestMessage}
              onActivateMessageVersion={onActivateMessageVersion}
            />
          ))}
        </Flex>
      )}
    </div>
  )
}

function TranscriptLoadingPlaceholders() {
  const { token } = theme.useToken()
  const placeholders = [
    {
      align: 'flex-end',
      background: token.colorPrimaryBg,
      border: token.colorPrimaryBorder,
      rows: 2,
      width: '58%',
    },
    {
      align: 'flex-start',
      background: token.colorFillQuaternary,
      border: token.colorBorderSecondary,
      rows: 3,
      width: '64%',
    },
    {
      align: 'flex-end',
      background: token.colorPrimaryBg,
      border: token.colorPrimaryBorder,
      rows: 1,
      width: '44%',
    },
    {
      align: 'flex-start',
      background: token.colorFillQuaternary,
      border: token.colorBorderSecondary,
      rows: 4,
      width: '70%',
    },
  ] as const

  return (
    <Flex vertical gap={12}>
      {placeholders.map((item, index) => (
        <Flex key={index} justify={item.align}>
          <div
            style={{
              width: item.width,
              maxWidth: '78%',
              borderRadius: 8,
              padding: '10px 12px',
              background: item.background,
              border: `1px solid ${item.border}`,
            }}
          >
            <Skeleton
              active
              title={false}
              paragraph={{
                rows: item.rows,
                width:
                  item.rows === 1 ? ['72%'] : ['96%', '82%', '68%', '54%'].slice(0, item.rows),
              }}
            />
          </div>
        </Flex>
      ))}
    </Flex>
  )
}
