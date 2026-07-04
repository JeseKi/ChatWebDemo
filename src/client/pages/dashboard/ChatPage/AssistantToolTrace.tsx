import { Space, Tag, Typography, theme } from 'antd'
import { ToolOutlined } from '@ant-design/icons'
import type { ToolCallTrace } from '../../../lib/chat'

export default function AssistantToolTrace({ toolCall }: { toolCall: ToolCallTrace }) {
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

const preStyle = {
  margin: '8px 0 0',
  whiteSpace: 'pre-wrap',
  overflowWrap: 'anywhere',
  fontSize: 12,
} as const
