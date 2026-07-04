import { useEffect, useRef, useState } from 'react'
import { Button, Tooltip, App } from 'antd'
import { CheckOutlined, CopyOutlined } from '@ant-design/icons'
import { copyText } from './clipboard'

const COPIED_RESET_DELAY_MS = 1000

export default function CopyButton({
  text,
  tooltip = '复制',
  className,
  disabled,
}: {
  text: string
  tooltip?: string
  className?: string
  disabled?: boolean
}) {
  const { message } = App.useApp()
  const [copied, setCopied] = useState(false)
  const resetTimerRef = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (resetTimerRef.current !== null) {
        window.clearTimeout(resetTimerRef.current)
      }
    }
  }, [])

  const handleCopy = async () => {
    if (copied) {
      return
    }

    const didCopy = await copyText(text)
    if (didCopy) {
      message.success('已复制')
      setCopied(true)
      resetTimerRef.current = window.setTimeout(() => {
        setCopied(false)
        resetTimerRef.current = null
      }, COPIED_RESET_DELAY_MS)
    } else {
      message.error('复制失败')
    }
  }

  return (
    <Tooltip title={tooltip}>
      <Button
        size="small"
        type="text"
        className={className}
        icon={copied ? <CheckOutlined /> : <CopyOutlined />}
        disabled={copied || disabled || !text}
        onClick={(event) => {
          event.stopPropagation()
          void handleCopy()
        }}
      />
    </Tooltip>
  )
}
