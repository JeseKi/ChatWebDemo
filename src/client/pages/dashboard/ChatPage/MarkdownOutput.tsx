import { isValidElement, useEffect, useState, type ComponentProps, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeExternalLinks from 'rehype-external-links'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'
import type { Options as SanitizeSchema } from 'rehype-sanitize'
import CopyButton from './CopyButton'

type ShikiBundle = typeof import('shiki/bundle/full')

let shikiBundlePromise: Promise<ShikiBundle> | null = null

const sanitizeSchema: SanitizeSchema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    a: [
      ...(defaultSchema.attributes?.a ?? []),
      'title',
      'target',
      'rel',
    ],
    img: [
      ...(defaultSchema.attributes?.img ?? []),
      'alt',
      'title',
      'width',
      'height',
      'loading',
    ],
    input: [
      ...(defaultSchema.attributes?.input ?? []),
      ['checked', true],
      ['readOnly', true],
      ['ariaChecked', 'true', 'false'],
    ],
  },
}

const markdownComponents: Components = {
  a: MarkdownLink,
  code: MarkdownCode,
  img: MarkdownImage,
  input: MarkdownInput,
  pre: MarkdownPre,
  table: MarkdownTable,
}

export default function MarkdownOutput({ content }: { content: string }) {
  return (
    <div className="chat-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[
          [rehypeExternalLinks, { rel: ['nofollow', 'noopener', 'noreferrer'], target: '_blank' }],
          [rehypeSanitize, sanitizeSchema],
        ]}
        components={markdownComponents}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

function MarkdownLink({ children, href, ...props }: ComponentProps<'a'>) {
  return (
    <a href={href} {...props}>
      {children}
    </a>
  )
}

function MarkdownImage({ alt, ...props }: ComponentProps<'img'>) {
  return <img alt={alt ?? ''} loading="lazy" {...props} />
}

function MarkdownInput(props: ComponentProps<'input'>) {
  if (props.type === 'checkbox') {
    return <input {...props} type="checkbox" readOnly disabled />
  }
  return <input {...props} readOnly />
}

function MarkdownTable({ children, ...props }: ComponentProps<'table'>) {
  return (
    <div className="chat-table-wrapper">
      <table {...props}>{children}</table>
    </div>
  )
}

function MarkdownCode({ children, className, ...props }: ComponentProps<'code'>) {
  return (
    <code className={className} {...props}>
      {children}
    </code>
  )
}

function MarkdownPre({ children }: ComponentProps<'pre'>) {
  const code = extractText(children)
  const language = extractLanguage(children)

  return (
    <div className="chat-code-block">
      <CopyButton text={code} tooltip="复制代码" className="chat-code-copy" />
      {language ? (
        <ShikiCodeBlock code={code} language={language} />
      ) : (
        <pre>
          <code>{code}</code>
        </pre>
      )}
    </div>
  )
}

function ShikiCodeBlock({ code, language }: { code: string; language: string }) {
  const [html, setHtml] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const theme = document.documentElement.dataset.theme === 'light' ? 'github-light' : 'github-dark'

    void loadShikiBundle()
      .then(({ codeToHtml }) =>
        codeToHtml(code, {
          lang: language,
          theme,
        }),
      )
      .then((highlighted) => {
        if (!cancelled) {
          setHtml(highlighted)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setHtml(null)
        }
      })

    return () => {
      cancelled = true
    }
  }, [code, language])

  if (!html) {
    return (
      <pre>
        <code className={`language-${language}`}>{code}</code>
      </pre>
    )
  }

  return <div className="chat-code-shiki" dangerouslySetInnerHTML={{ __html: html }} />
}

function loadShikiBundle(): Promise<ShikiBundle> {
  shikiBundlePromise ??= import('shiki/bundle/full')
  return shikiBundlePromise
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

function extractLanguage(node: ReactNode): string | null {
  if (Array.isArray(node)) {
    return node.map(extractLanguage).find(Boolean) ?? null
  }
  if (!isValidElement<{ className?: string; children?: ReactNode }>(node)) {
    return null
  }
  const className = node.props.className ?? ''
  const match = /language-([^\s]+)/.exec(className)
  return match?.[1] ?? extractLanguage(node.props.children)
}
