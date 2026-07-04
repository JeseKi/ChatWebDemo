import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { App, Empty, Flex, Result, Spin, Typography, theme } from 'antd'
import * as chatApi from '../../../lib/chat'
import type { SharedChatSession } from '../../../lib/chat'
import SharedMessageBubble from './SharedMessageBubble'
import { resolveErrorMessage } from './utils'

export default function SharedChatPage() {
  const { token } = useParams<{ token: string }>()
  const { message } = App.useApp()
  const { token: themeToken } = theme.useToken()
  const [share, setShare] = useState<SharedChatSession | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const loadShare = async () => {
      if (!token) {
        setError('分享链接无效')
        setLoading(false)
        return
      }
      setLoading(true)
      try {
        const detail = await chatApi.getSharedChatSession(token)
        setShare(detail)
        setError(null)
      } catch (err) {
        const text = resolveErrorMessage(err)
        setError(text)
        message.error(text)
      } finally {
        setLoading(false)
      }
    }

    void loadShare()
  }, [message, token])

  if (loading) {
    return (
      <Flex align="center" justify="center" style={{ minHeight: '100vh' }}>
        <Spin />
      </Flex>
    )
  }

  if (error || !share) {
    return <Result status="404" title="分享不存在" subTitle={error ?? '该分享链接不可用'} />
  }

  return (
    <Flex
      vertical
      gap={16}
      style={{
        minHeight: '100vh',
        padding: 24,
        background: themeToken.colorBgLayout,
      }}
    >
      <Flex vertical gap={4} style={{ maxWidth: 980, width: '100%', margin: '0 auto' }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          {share.title}
        </Typography.Title>
        <Typography.Text type="secondary">
          分享于 {new Date(share.created_at).toLocaleString()}
        </Typography.Text>
      </Flex>

      <Flex
        vertical
        gap={12}
        style={{
          maxWidth: 980,
          width: '100%',
          margin: '0 auto',
          border: `1px solid ${themeToken.colorBorder}`,
          borderRadius: 8,
          padding: 16,
          background: themeToken.colorBgContainer,
        }}
      >
        {share.messages.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="该分享没有消息" />
        ) : (
          share.messages.map((item) => <SharedMessageBubble key={item.id} message={item} />)
        )}
      </Flex>
    </Flex>
  )
}
