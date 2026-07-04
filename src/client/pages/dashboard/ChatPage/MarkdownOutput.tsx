import { isValidElement, type ComponentProps, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import CopyButton from './CopyButton'

export default function MarkdownOutput({ content }: { content: string }) {
  return (
    <div className="chat-markdown">
      <ReactMarkdown components={{ pre: MarkdownPre }}>{content}</ReactMarkdown>
    </div>
  )
}

function MarkdownPre({ children, ...props }: ComponentProps<'pre'>) {
  const code = extractText(children)

  return (
    <div className="chat-code-block">
      <CopyButton text={code} tooltip="复制代码" className="chat-code-copy" />
      <pre {...props}>{children}</pre>
    </div>
  )
}

function extractText(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') {
    return String(node)
  }
  if (Array.isArray(node)) {
    return node.map(extractText).join('')
  }
  if (isValidElement<{ children?: ReactNode }>(node)) {
    return extractText(node.props.children)
  }
  return ''
}
