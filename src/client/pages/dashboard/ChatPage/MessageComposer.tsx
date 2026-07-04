import { Button, Flex, Input } from 'antd'
import { SendOutlined, StopOutlined } from '@ant-design/icons'

export default function MessageComposer({
  input,
  streaming,
  onInputChange,
  onSendMessage,
  onStopStreaming,
}: {
  input: string
  streaming: boolean
  onInputChange: (value: string) => void
  onSendMessage: () => void
  onStopStreaming: () => void
}) {
  return (
    <Flex gap={8} style={{ marginTop: 12 }}>
      <Input.TextArea
        value={input}
        disabled={streaming}
        autoSize={{ minRows: 2, maxRows: 5 }}
        placeholder="输入消息"
        onChange={(event) => onInputChange(event.target.value)}
        onPressEnter={(event) => {
          if (!event.shiftKey) {
            event.preventDefault()
            onSendMessage()
          }
        }}
      />
      {streaming ? (
        <Button danger icon={<StopOutlined />} onClick={onStopStreaming}>
          停止
        </Button>
      ) : (
        <Button type="primary" icon={<SendOutlined />} onClick={onSendMessage}>
          发送
        </Button>
      )}
    </Flex>
  )
}
