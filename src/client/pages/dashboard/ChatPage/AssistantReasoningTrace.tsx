import { Flex, Typography, theme } from 'antd'
import { RightOutlined } from '@ant-design/icons'
import { useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import MarkdownOutput from './MarkdownOutput'

export default function AssistantReasoningTrace({ content }: { content: string }) {
  const { token } = theme.useToken()
  const [open, setOpen] = useState(false)

  return (
    <div
      style={{
        border: `1px solid ${token.colorBorderSecondary}`,
        borderRadius: 6,
        background: token.colorFillQuaternary,
      }}
    >
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
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
        <Flex align="center" gap={8}>
          <RightOutlined
            style={{
              fontSize: 12,
              transform: open ? 'rotate(90deg)' : 'rotate(0deg)',
              transition: 'transform 180ms ease',
            }}
          />
          <Typography.Text type="secondary">思考过程</Typography.Text>
        </Flex>
      </button>

      <AnimatedCollapse open={open}>
        <div
          style={{
            borderTop: `1px solid ${token.colorBorderSecondary}`,
            padding: 10,
          }}
        >
          <div className="chat-reasoning-markdown" style={preLikeStyle}>
            <MarkdownOutput content={content || ' '} />
          </div>
        </div>
      </AnimatedCollapse>
    </div>
  )
}

function AnimatedCollapse({ open, children }: { open: boolean; children: ReactNode }) {
  return (
    <div
      aria-hidden={!open}
      style={{
        display: 'grid',
        gridTemplateRows: open ? '1fr' : '0fr',
        opacity: open ? 1 : 0,
        overflow: 'hidden',
        pointerEvents: open ? undefined : 'none',
        transition: `grid-template-rows 180ms ease, opacity 160ms ease, visibility 0s linear ${
          open ? '0s' : '180ms'
        }`,
        visibility: open ? 'visible' : 'hidden',
      }}
    >
      <div style={{ minHeight: 0, overflow: 'hidden' }}>{children}</div>
    </div>
  )
}

const preLikeStyle: CSSProperties = {
  margin: 0,
  overflowWrap: 'anywhere',
  fontSize: 12,
  lineHeight: 1.55,
}
