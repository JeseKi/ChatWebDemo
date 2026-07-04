import { Image, Space, Typography } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { getApiBaseUrl } from '../../../lib/api'
import { getAccessToken } from '../../../lib/tokenStorage'

const IMAGE_PATTERN = /<\|IMAGE\|>(.*?)<\/\|IMAGE\|>/g

type Segment =
  | { type: 'text'; value: string; key: string }
  | { type: 'image'; value: string; key: string }

export default function MessageContent({
  content,
  shared = false,
}: {
  content: string
  shared?: boolean
}) {
  const segments = useMemo(() => parseSegments(content), [content])
  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      {segments.map((segment) =>
        segment.type === 'text' ? (
          segment.value ? (
            <Typography.Text
              key={segment.key}
              style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}
            >
              {segment.value}
            </Typography.Text>
          ) : null
        ) : (
          <ChatImage key={segment.key} url={segment.value} shared={shared} />
        ),
      )}
    </Space>
  )
}

function ChatImage({ url, shared }: { url: string; shared: boolean }) {
  const [src, setSrc] = useState<string | null>(shared ? normalizeImageUrl(url) : null)

  useEffect(() => {
    if (shared) {
      setSrc(normalizeImageUrl(url))
      return undefined
    }
    let revokedUrl: string | null = null
    let cancelled = false
    const token = getAccessToken()
    fetch(normalizeImageUrl(url), {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      credentials: 'include',
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Image request failed: ${response.status}`)
        }
        return response.blob()
      })
      .then((blob) => {
        if (cancelled) return
        revokedUrl = URL.createObjectURL(blob)
        setSrc(revokedUrl)
      })
      .catch(() => {
        if (!cancelled) setSrc(null)
      })
    return () => {
      cancelled = true
      if (revokedUrl) URL.revokeObjectURL(revokedUrl)
    }
  }, [shared, url])

  if (!src) {
    return <Typography.Text type="secondary">[图片无法加载]</Typography.Text>
  }
  return (
    <Image
      src={src}
      alt="聊天图片"
      style={{ maxWidth: 280, borderRadius: 8, display: 'block' }}
      preview={{ src }}
    />
  )
}

function parseSegments(content: string): Segment[] {
  const segments: Segment[] = []
  let lastIndex = 0
  let index = 0
  for (const match of content.matchAll(IMAGE_PATTERN)) {
    const start = match.index ?? 0
    if (start > lastIndex) {
      segments.push({
        type: 'text',
        value: content.slice(lastIndex, start).trim(),
        key: `text-${index}`,
      })
      index += 1
    }
    segments.push({ type: 'image', value: match[1], key: `image-${index}` })
    index += 1
    lastIndex = start + match[0].length
  }
  if (lastIndex < content.length || segments.length === 0) {
    segments.push({
      type: 'text',
      value: content.slice(lastIndex).trim(),
      key: `text-${index}`,
    })
  }
  return segments
}

function normalizeImageUrl(url: string): string {
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return url
  }
  if (url.startsWith('/api/')) {
    return url
  }
  const baseUrl = getApiBaseUrl()
  return `${baseUrl}${url.startsWith('/') ? url : `/${url}`}`
}
