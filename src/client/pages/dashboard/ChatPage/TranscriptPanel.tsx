import type { RefObject } from 'react'
import { Collapse, Empty, Flex, Skeleton, Tag, Typography, theme } from 'antd'
import type { ChatContextCompression, ChatMessage } from '../../../lib/chat'
import MarkdownOutput from './MarkdownOutput'
import MessageBubble from './MessageBubble'

type TranscriptItem =
  | { type: 'message'; message: ChatMessage }
  | { type: 'compression'; compression: ChatContextCompression }

export default function TranscriptPanel({
  transcriptRef,
  messages,
  contextCompressions,
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
  contextCompressions: ChatContextCompression[]
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
  const transcriptItems = buildTranscriptItems(messages, contextCompressions)
  const latestMessageId = messages[messages.length - 1]?.id

  return (
    <div
      ref={transcriptRef}
      style={{
        flex: 1,
        minHeight: 0,
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
          {transcriptItems.map((item) =>
            item.type === 'compression' ? (
              <ContextCompressionMessage
                key={`compression-${item.compression.id}`}
                compression={item.compression}
              />
            ) : (
              <MessageBubble
                key={item.message.id}
                message={item.message}
                isLatest={item.message.id === latestMessageId}
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
            ),
          )}
        </Flex>
      )}
    </div>
  )
}

function buildTranscriptItems(
  messages: ChatMessage[],
  compressions: ChatContextCompression[],
): TranscriptItem[] {
  const activeCompressions = compressions
    .filter((item) => item.applies_to_active_path)
    .sort((a, b) => a.head_end_message_id - b.head_end_message_id || a.id - b.id)
  const activeCompression = activeCompressions[activeCompressions.length - 1]
  const items: TranscriptItem[] = []

  for (const message of messages) {
    if (activeCompression && message.id === activeCompression.tail_start_message_id) {
      items.push({ type: 'compression', compression: activeCompression })
    }
    items.push({ type: 'message', message })
  }

  return items
}

function ContextCompressionMessage({
  compression,
}: {
  compression: ChatContextCompression
}) {
  const { token } = theme.useToken()

  return (
    <Flex justify="center">
      <div
        style={{
          width: '78%',
          maxWidth: '100%',
          borderRadius: 8,
          padding: '8px 10px',
          background: token.colorFillQuaternary,
          border: `1px dashed ${token.colorBorder}`,
        }}
      >
        <Flex vertical gap={6}>
          <Flex align="center" justify="space-between" gap={8} wrap>
            <Tag color="blue" style={{ marginInlineEnd: 0 }}>
              上下文已压缩
            </Tag>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {new Date(compression.created_at).toLocaleString()}
            </Typography.Text>
          </Flex>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            覆盖至消息 {compression.head_end_message_id} · 保留从消息{' '}
            {compression.tail_start_message_id} 开始 · {compression.original_token_estimate} →{' '}
            {compression.summary_token_estimate} tokens
          </Typography.Text>
          <Collapse
            ghost
            size="small"
            items={[
              {
                key: String(compression.id),
                label: '查看压缩摘要',
                children: <MarkdownOutput content={compression.summary} />,
              },
            ]}
          />
        </Flex>
      </div>
    </Flex>
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
