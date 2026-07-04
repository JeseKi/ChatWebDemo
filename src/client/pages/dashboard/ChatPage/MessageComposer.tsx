import { Input } from 'antd'
import { ArrowUp } from 'lucide-react'

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
  const canSend = input.trim().length > 0 && !streaming

  return (
    <div className="chat-composer">
      <Input.TextArea
        value={input}
        disabled={streaming}
        autoSize={{ minRows: 1, maxRows: 8 }}
        className="chat-composer-input"
        placeholder="有问题，尽管问"
        onChange={(event) => onInputChange(event.target.value)}
        onPressEnter={(event) => {
          if (!event.shiftKey) {
            event.preventDefault()
            if (canSend) {
              onSendMessage()
            }
          }
        }}
      />
      <div className="chat-composer-toolbar">
        <div />
        {streaming ? (
          <button
            type="button"
            className="chat-composer-action chat-composer-action-active"
            aria-label="停止生成"
            onClick={onStopStreaming}
          >
            <span className="chat-composer-stop-icon" />
          </button>
        ) : (
          <button
            type="button"
            className="chat-composer-action"
            aria-label="发送消息"
            disabled={!canSend}
            onClick={onSendMessage}
          >
            <ArrowUp size={20} strokeWidth={2.4} />
          </button>
        )}
      </div>
    </div>
  )
}
