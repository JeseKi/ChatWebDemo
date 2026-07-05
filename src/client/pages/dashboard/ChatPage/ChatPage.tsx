import { Button, Drawer, Flex, Spin, Tag, Tooltip, Typography, theme } from 'antd'
import {
  MenuOutlined,
  ShareAltOutlined,
} from '@ant-design/icons'
import { useState } from 'react'
import MessageComposer from './MessageComposer'
import ShareSessionModal from './ShareSessionModal'
import SessionSidebar from './SessionSidebar'
import TranscriptPanel from './TranscriptPanel'
import { useChatPageController } from './useChatPageController'

export default function ChatPage() {
  const chat = useChatPageController()
  const { token } = theme.useToken()
  const [sessionDrawerOpen, setSessionDrawerOpen] = useState(false)

  const closeSessionDrawer = () => setSessionDrawerOpen(false)

  const handleStartNewSession = () => {
    chat.startNewSession()
    closeSessionDrawer()
  }

  const handleLoadSession = (sessionId: string) => {
    void chat.loadSession(sessionId)
    closeSessionDrawer()
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        background: token.colorBgLayout,
      }}
    >
      <header
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 20,
          display: 'grid',
          gridTemplateColumns: 'minmax(120px, 1fr) minmax(0, 920px) minmax(120px, 1fr)',
          alignItems: 'center',
          gap: 12,
          minHeight: 64,
          padding: '10px 16px',
          background: token.colorBgLayout,
          borderBottom: `1px solid ${token.colorBorder}`,
        }}
      >
        <Flex align="center" justify="flex-start" style={{ minWidth: 0 }}>
          <Tooltip title="对话列表">
            <Button
              type="text"
              icon={<MenuOutlined />}
              onClick={() => setSessionDrawerOpen(true)}
            />
          </Tooltip>
        </Flex>

        <Flex vertical align="center" style={{ minWidth: 0 }}>
          <Typography.Title
            level={5}
            ellipsis={{ tooltip: chat.activeSession?.title ?? '新对话' }}
            style={{ margin: 0, maxWidth: '100%' }}
          >
            {chat.activeSession?.title ?? '新对话'}
          </Typography.Title>
        </Flex>

        <Flex align="center" justify="flex-end" gap={8} style={{ minWidth: 0 }}>
          {chat.streaming && (
            <Tag color="processing" icon={<Spin size="small" />}>
              生成中
            </Tag>
          )}
          <Tooltip title="分享当前会话">
            <Button
              icon={<ShareAltOutlined />}
              loading={chat.sharing}
              disabled={!chat.activeSessionId || chat.streaming || chat.loadingMessages}
              onClick={() => void chat.shareActiveSession()}
            />
          </Tooltip>
        </Flex>
      </header>

      <main
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(24px, 1fr) minmax(0, 920px) minmax(24px, 1fr)',
          height: 'calc(100vh - 64px)',
          padding: '16px 0 24px',
        }}
      >
        <div />
        <Flex vertical style={{ height: '100%', minHeight: 0, minWidth: 0 }}>
          <TranscriptPanel
            transcriptRef={chat.transcriptRef}
            messages={chat.messages}
            contextCompressions={chat.contextCompressions}
            loadingMessages={chat.loadingMessages}
            streaming={chat.streaming}
            editingMessageId={chat.editingMessageId}
            editingMessageContent={chat.editingMessageContent}
            onStartEditingMessage={chat.startEditingMessage}
            onEditingMessageContentChange={chat.setEditingMessageContent}
            onCancelEditingMessage={chat.cancelEditingMessage}
            onSaveEditedMessage={chat.saveEditedMessage}
            onRegenerateLatestMessage={chat.regenerateLatestMessage}
            onActivateMessageVersion={chat.activateMessageVersion}
          />

          <MessageComposer
            input={chat.input}
            models={chat.models}
            selectedModelId={chat.selectedModelId}
            selectedVariant={chat.selectedVariant}
            selectedModelThinkingEntries={chat.selectedModelThinkingEntries}
            pendingImageFiles={chat.pendingImageFiles}
            disabledReason={chat.composerDisabledReason}
            streaming={chat.streaming}
            onInputChange={chat.setInput}
            onSelectedModelChange={chat.setSelectedModelId}
            onSelectedVariantChange={chat.setSelectedVariant}
            onAddImageFiles={chat.addPendingImageFiles}
            onRemoveImageFile={chat.removePendingImageFile}
            onSendMessage={() => void chat.sendMessage()}
            onStopStreaming={chat.stopStreaming}
          />
        </Flex>
        <div />
      </main>

      <Drawer
        open={sessionDrawerOpen}
        placement="left"
        width="min(340px, 92vw)"
        closable={false}
        onClose={closeSessionDrawer}
        styles={{
          body: { padding: 16, height: '100%' },
        }}
      >
        <SessionSidebar
          sessions={chat.sessions}
          activeSessionId={chat.activeSessionId}
          loadingSessions={chat.loadingSessions}
          editingSessionId={chat.editingSessionId}
          editingTitle={chat.editingTitle}
          mutatingSessionId={chat.mutatingSessionId}
          onStartNewSession={handleStartNewSession}
          onLoadSession={handleLoadSession}
          onStartEditingSession={chat.startEditingSession}
          onEditingTitleChange={chat.setEditingTitle}
          onCancelEditingSession={chat.cancelEditingSession}
          onSaveSessionTitle={(sessionId) => void chat.saveSessionTitle(sessionId)}
          onDeleteSession={(sessionId) => void chat.deleteSession(sessionId)}
          onClose={closeSessionDrawer}
        />
      </Drawer>

      <ShareSessionModal
        open={chat.shareModalOpen}
        loading={chat.sharing}
        share={chat.activeShare}
        messages={chat.messages}
        onClose={chat.closeShareModal}
      />
    </div>
  )
}
