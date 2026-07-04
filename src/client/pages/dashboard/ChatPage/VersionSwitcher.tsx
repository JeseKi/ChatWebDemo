import { Button, Space, Typography } from 'antd'
import { LeftOutlined, RightOutlined } from '@ant-design/icons'
import type { ChatMessage } from '../../../lib/chat'

export default function VersionSwitcher({
  message,
  disabled,
  onActivateMessageVersion,
}: {
  message: ChatMessage
  disabled: boolean
  onActivateMessageVersion: (messageId: number, targetMessageId: number) => Promise<void>
}) {
  if (message.version_count <= 1) {
    return null
  }
  return (
    <Space size={2}>
      <Button
        size="small"
        type="text"
        icon={<LeftOutlined />}
        disabled={disabled || message.previous_version_message_id === null}
        onClick={() => {
          if (message.previous_version_message_id !== null) {
            void onActivateMessageVersion(message.id, message.previous_version_message_id)
          }
        }}
      />
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {message.version_position}/{message.version_count}
      </Typography.Text>
      <Button
        size="small"
        type="text"
        icon={<RightOutlined />}
        disabled={disabled || message.next_version_message_id === null}
        onClick={() => {
          if (message.next_version_message_id !== null) {
            void onActivateMessageVersion(message.id, message.next_version_message_id)
          }
        }}
      />
    </Space>
  )
}
