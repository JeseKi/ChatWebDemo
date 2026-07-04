import { Image, Input, Popover, Tooltip, Typography } from 'antd'
import { ArrowUp, Check, ChevronDown, ImagePlus, X } from 'lucide-react'
import {
  type ClipboardEvent,
  type CSSProperties,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { ThemeContext, type ResolvedTheme } from '../../../contexts/ThemeContext'
import type { ChatModel, ChatModelIcon, ChatModelIconMode } from '../../../lib/chat'

export default function MessageComposer({
  input,
  models,
  selectedModelId,
  selectedVariant,
  selectedModelThinkingEntries,
  pendingImageFiles,
  disabledReason,
  streaming,
  onInputChange,
  onSelectedModelChange,
  onSelectedVariantChange,
  onAddImageFiles,
  onRemoveImageFile,
  onSendMessage,
  onStopStreaming,
}: {
  input: string
  models: ChatModel[]
  selectedModelId: string | null
  selectedVariant: string | null
  selectedModelThinkingEntries: [string, string][]
  pendingImageFiles: File[]
  disabledReason: string | null
  streaming: boolean
  onInputChange: (value: string) => void
  onSelectedModelChange: (value: string) => void
  onSelectedVariantChange: (value: string | null) => void
  onAddImageFiles: (files: File[]) => void
  onRemoveImageFile: (index: number) => void
  onSendMessage: () => void
  onStopStreaming: () => void
}) {
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [modelMenuOpen, setModelMenuOpen] = useState(false)
  const canSend = (input.trim().length > 0 || pendingImageFiles.length > 0) && !streaming && !disabledReason
  const selectedModel = models.find((model) => model.id === selectedModelId) ?? null
  const [imagePreviewUrls, setImagePreviewUrls] = useState<string[]>([])
  const selectedVariantLabel = selectedModelThinkingEntries.find(([value]) => value === selectedVariant)?.[1]
    ?? selectedModelThinkingEntries[0]?.[1]
    ?? null
  const modelMenu = useMemo(() => (
    <div className="chat-model-menu">
      <div className="chat-model-menu-list">
        {models.map((model) => {
          const active = model.id === selectedModelId
          return (
            <button
              type="button"
              key={model.id}
              className={`chat-model-option${active ? ' chat-model-option-active' : ''}`}
              onClick={() => {
                onSelectedModelChange(model.id)
                if (Object.keys(model.thinking).length === 0) {
                  setModelMenuOpen(false)
                }
              }}
            >
              <ModelIcon icon={model.icon} label={model.name} />
              <span className="chat-model-option-main">
                <span className="chat-model-option-name">{model.name}</span>
                <span className="chat-model-option-meta">{formatProviderName(model.provider)} · {model.id}</span>
              </span>
              {active && <Check size={16} />}
            </button>
          )
        })}
      </div>
      {selectedModelThinkingEntries.length > 0 && (
        <div className="chat-model-variant-panel">
          <div className="chat-model-menu-title">思考</div>
          <div className="chat-model-variants">
            {selectedModelThinkingEntries.map(([value, label]) => (
              <button
                type="button"
                key={value}
                className={`chat-model-variant${value === selectedVariant ? ' chat-model-variant-active' : ''}`}
                onClick={() => {
                  onSelectedVariantChange(value)
                  setModelMenuOpen(false)
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  ), [
    models,
    onSelectedModelChange,
    onSelectedVariantChange,
    selectedModelId,
    selectedModelThinkingEntries,
    selectedVariant,
  ])
  const handlePaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const files = extractClipboardImageFiles(event.clipboardData)
    if (files.length === 0) return
    event.preventDefault()
    onAddImageFiles(files)
  }

  useEffect(() => {
    const urls = pendingImageFiles.map((file) => URL.createObjectURL(file))
    setImagePreviewUrls(urls)
    return () => {
      urls.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [pendingImageFiles])

  return (
    <div className="chat-composer">
      {disabledReason && (
        <Typography.Text className="chat-composer-warning">
          {disabledReason}
        </Typography.Text>
      )}
      <Input.TextArea
        value={input}
        disabled={streaming || models.length === 0}
        autoSize={{ minRows: 1, maxRows: 8 }}
        className="chat-composer-input"
        placeholder="有问题，尽管问"
        onChange={(event) => onInputChange(event.target.value)}
        onPaste={handlePaste}
        onPressEnter={(event) => {
          if (event.ctrlKey) {
            event.preventDefault()
            if (canSend) {
              onSendMessage()
            }
          }
        }}
      />
      {pendingImageFiles.length > 0 && (
        <div className="chat-composer-attachments">
          {pendingImageFiles.map((file, index) => (
            <div className="chat-composer-attachment" key={`${file.name}-${index}`}>
              {imagePreviewUrls[index] && (
                <Image
                  src={imagePreviewUrls[index]}
                  alt={file.name}
                  width={70}
                  height={70}
                  className="chat-composer-attachment-preview"
                  preview={{ src: imagePreviewUrls[index] }}
                />
              )}
              <span className="chat-composer-attachment-name" title={file.name}>
                {file.name || '图片'}
              </span>
              <button
                type="button"
                aria-label="移除图片"
                onClick={() => onRemoveImageFile(index)}
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
      <div className="chat-composer-toolbar">
        <div className="chat-composer-controls">
          <Popover
            open={modelMenuOpen}
            trigger="click"
            placement="topLeft"
            arrow={false}
            overlayClassName="chat-model-popover"
            content={modelMenu}
            onOpenChange={(open) => setModelMenuOpen(open)}
          >
            <button
              type="button"
              className="chat-model-trigger"
              disabled={streaming || models.length === 0}
            >
              <ModelIcon icon={selectedModel?.icon ?? null} label={selectedModel?.name ?? '模型'} />
              <span className="chat-model-trigger-text">
                <span>{selectedModel?.name ?? '选择模型'}</span>
                {selectedVariantLabel && <span>{selectedVariantLabel}</span>}
              </span>
              <ChevronDown size={15} />
            </button>
          </Popover>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            multiple
            hidden
            onChange={(event) => {
              onAddImageFiles(Array.from(event.target.files ?? []))
              event.target.value = ''
            }}
          />
          <Tooltip title={selectedModel?.visual ? '上传图片' : '当前模型不支持图片'}>
            <button
              type="button"
              className="chat-composer-secondary-action"
              disabled={streaming || !selectedModel?.visual}
              aria-label="上传图片"
              onClick={() => fileInputRef.current?.click()}
            >
              <ImagePlus size={18} />
            </button>
          </Tooltip>
        </div>
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

function extractClipboardImageFiles(clipboardData: DataTransfer): File[] {
  const files = [
    ...Array.from(clipboardData.files),
    ...Array.from(clipboardData.items)
      .filter((item) => item.kind === 'file')
      .map((item) => item.getAsFile())
      .filter((file): file is File => file !== null),
  ].filter((file) => file.type.startsWith('image/'))

  const seen = new Set<string>()
  return files.filter((file) => {
    const key = `${file.name}:${file.type}:${file.size}:${file.lastModified}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function formatProviderName(provider: string): string {
  if (provider.startsWith('openai_') || provider === 'openai') return 'OpenAI'
  if (provider === 'anthropic') return 'Anthropic'
  if (provider === 'deepseek') return 'Deepseek'
  if (provider === 'google') return 'Google'
  return provider
}

function ModelIcon({ icon, label }: { icon?: ChatModelIcon; label: string }) {
  const themeContext = useContext(ThemeContext)
  const resolved = resolveModelIcon(icon, themeContext?.resolvedTheme ?? 'light')
  if (resolved?.renderMode === 'mask') {
    return (
      <span
        className="chat-model-icon chat-model-icon-mask"
        style={{ '--chat-model-icon-src': `url(${JSON.stringify(resolved.src)})` } as ModelIconStyle}
        aria-hidden="true"
      />
    )
  }
  if (resolved) {
    return (
      <span className="chat-model-icon">
        <img src={resolved.src} alt="" referrerPolicy="no-referrer" />
      </span>
    )
  }
  return (
    <span className="chat-model-icon chat-model-icon-fallback" aria-hidden="true">
      {label.trim().slice(0, 1).toUpperCase() || 'M'}
    </span>
  )
}

type ModelIconStyle = CSSProperties & {
  '--chat-model-icon-src'?: string
}

interface ResolvedModelIcon {
  src: string
  renderMode: Exclude<ChatModelIconMode, 'auto'>
}

function resolveModelIcon(icon: ChatModelIcon | undefined, theme: ResolvedTheme): ResolvedModelIcon | null {
  const source = typeof icon === 'string'
    ? icon
    : theme === 'dark'
      ? icon?.dark ?? icon?.light
      : icon?.light ?? icon?.dark
  const src = resolveIconSource(source)
  if (!src) return null

  const configuredMode = typeof icon === 'string' ? 'auto' : icon?.mode ?? 'auto'
  if (configuredMode === 'image') {
    return { src, renderMode: 'image' }
  }
  if (configuredMode === 'mask' || shouldRenderIconAsMask(source ?? '', src)) {
    return { src, renderMode: 'mask' }
  }
  return { src, renderMode: 'image' }
}

function resolveIconSource(icon?: string | null): string | null {
  const value = icon?.trim()
  if (!value) return null
  if (value.startsWith('<svg')) {
    return `data:image/svg+xml;utf8,${encodeURIComponent(value)}`
  }
  if (/^(https?:\/\/|data:image\/|\/)/i.test(value)) {
    return value
  }
  if (/^[A-Za-z0-9+/]+={0,2}$/.test(value)) {
    try {
      const decoded = window.atob(value)
      const mimeType = decoded.trimStart().startsWith('<svg')
        ? 'image/svg+xml'
        : value.startsWith('/9j/')
          ? 'image/jpeg'
          : value.startsWith('UklGR')
            ? 'image/webp'
            : 'image/png'
      return `data:${mimeType};base64,${value}`
    } catch {
      return null
    }
  }
  return null
}

function shouldRenderIconAsMask(raw: string, src: string): boolean {
  const value = raw.trim().toLowerCase()
  if (!value) return false
  if (value.startsWith('<svg') || src.startsWith('data:image/svg+xml')) {
    return !looksLikeColorIcon(value)
  }
  if (value.endsWith('.svg')) {
    return !looksLikeColorIcon(value)
  }
  return false
}

function looksLikeColorIcon(value: string): boolean {
  return value.includes('-color') || value.includes('brand-color')
}
