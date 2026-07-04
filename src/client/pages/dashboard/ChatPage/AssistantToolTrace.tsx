import { Button, Flex, Tag, Typography, theme } from 'antd'
import { DownOutlined, RightOutlined } from '@ant-design/icons'
import { useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import type { ToolCallTrace, ToolCallStatus } from '../../../lib/chat'

export default function AssistantToolTrace({ toolCall }: { toolCall: ToolCallTrace }) {
  const { token } = theme.useToken()
  const [toolOpen, setToolOpen] = useState(false)
  const [argumentsOpen, setArgumentsOpen] = useState(false)
  const [resultOpen, setResultOpen] = useState(false)
  const displayName = toolCall.display_name || toolCall.name
  const resultText = formatValue(toolCall.result)
  const hasResult =
    toolCall.status !== 'running' || (toolCall.result !== null && toolCall.result !== undefined)

  return (
    <div
      style={{
        border: `1px solid ${token.colorBorder}`,
        borderRadius: 6,
        background: token.colorBgElevated,
      }}
    >
      <button
        type="button"
        aria-expanded={toolOpen}
        onClick={() => setToolOpen((value) => !value)}
        style={{
          width: '100%',
          border: 0,
          padding: 10,
          background: 'transparent',
          color: 'inherit',
          cursor: 'pointer',
          textAlign: 'start',
        }}
      >
        <Flex align="center" gap={8} wrap="wrap">
          {toolOpen ? <DownOutlined /> : <RightOutlined />}
          <span aria-hidden="true" style={{ lineHeight: 1 }}>
            🛠
          </span>
          <Typography.Text strong ellipsis={{ tooltip: displayName }}>
            {displayName}
          </Typography.Text>
          <Tag color={getStatusColor(toolCall.status)} style={{ marginInlineEnd: 0 }}>
            {getStatusText(toolCall.status)}
          </Tag>
        </Flex>
      </button>

      {toolOpen && (
        <Flex
          vertical
          gap={8}
          style={{
            borderTop: `1px solid ${token.colorBorderSecondary}`,
            padding: 10,
          }}
        >
          <ToolTraceSection
            title="参数"
            open={argumentsOpen}
            maxHeight={220}
            onToggle={() => setArgumentsOpen((value) => !value)}
          >
            <pre style={preStyle}>{formatValue(toolCall.arguments)}</pre>
          </ToolTraceSection>

          <ToolTraceSection
            title="结果"
            open={resultOpen}
            maxHeight={320}
            onToggle={() => setResultOpen((value) => !value)}
          >
            {hasResult ? (
              <pre style={preStyle}>{resultText}</pre>
            ) : (
              <Typography.Text type="secondary">等待结果...</Typography.Text>
            )}
          </ToolTraceSection>
        </Flex>
      )}
    </div>
  )
}

function ToolTraceSection({
  title,
  open,
  maxHeight,
  children,
  onToggle,
}: {
  title: string
  open: boolean
  maxHeight: number
  children: ReactNode
  onToggle: () => void
}) {
  const { token } = theme.useToken()

  return (
    <div
      style={{
        border: `1px solid ${token.colorBorderSecondary}`,
        borderRadius: 6,
        background: token.colorFillQuaternary,
      }}
    >
      <Button
        block
        type="text"
        size="small"
        icon={open ? <DownOutlined /> : <RightOutlined />}
        aria-expanded={open}
        onClick={onToggle}
        style={{
          height: 28,
          justifyContent: 'flex-start',
          paddingInline: 8,
          color: token.colorTextSecondary,
        }}
      >
        {title}
      </Button>
      {open && (
        <div
          style={{
            maxHeight,
            overflow: 'auto',
            borderTop: `1px solid ${token.colorBorderSecondary}`,
            padding: 8,
          }}
        >
          {children}
        </div>
      )}
    </div>
  )
}

function getStatusColor(status: ToolCallStatus) {
  if (status === 'completed') {
    return 'success'
  }
  if (status === 'failed') {
    return 'error'
  }
  return 'processing'
}

function getStatusText(status: ToolCallStatus) {
  if (status === 'completed') {
    return '已完成'
  }
  if (status === 'failed') {
    return '失败'
  }
  return '执行中'
}

function formatValue(value: unknown): string {
  if (value === undefined) {
    return ''
  }
  if (typeof value === 'string') {
    return value
  }
  try {
    const serialized = JSON.stringify(value, null, 2)
    return serialized ?? String(value)
  } catch {
    return String(value)
  }
}

const preStyle: CSSProperties = {
  margin: 0,
  whiteSpace: 'pre-wrap',
  overflowWrap: 'anywhere',
  fontSize: 12,
  lineHeight: 1.55,
}
