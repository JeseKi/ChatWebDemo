import { Empty, Flex, Input, Modal, Spin, Tag, Typography, theme } from 'antd'
import type { ChatMessage, ChatSessionShare } from '../../../lib/chat'
import CopyButton from './CopyButton'
import MarkdownOutput from './MarkdownOutput'

const PREVIEW_MESSAGE_COUNT = 4

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
  const previewMessages = messages.slice(0, PREVIEW_MESSAGE_COUNT)

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
          {previewMessages.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无消息" />
          ) : (
            previewMessages.map((message) => (
              <PreviewMessage key={message.id} message={message} />
            ))
          )}
          {messages.length > PREVIEW_MESSAGE_COUNT && (
            <Typography.Text type="secondary">
              还有 {messages.length - PREVIEW_MESSAGE_COUNT} 条消息
            </Typography.Text>
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

  return (
    <Flex vertical gap={4}>
      <Tag color={color} style={{ width: 'fit-content' }}>
        {roleLabel}
      </Tag>
      <div className="chat-share-preview-markdown">
        <MarkdownOutput content={message.content || ' '} />
      </div>
    </Flex>
  )
}

function resolveShareUrl(value: string): string {
  if (!value) {
    return ''
  }
  return value.startsWith('/') ? `${window.location.origin}${value}` : value
}
