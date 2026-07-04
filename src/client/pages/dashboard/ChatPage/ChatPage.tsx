import { Button, Flex, Spin, Tag, Tooltip, Typography } from 'antd'
import { ShareAltOutlined } from '@ant-design/icons'
import MessageComposer from './MessageComposer'
import ShareSessionModal from './ShareSessionModal'
import SessionSidebar from './SessionSidebar'
import TranscriptPanel from './TranscriptPanel'
import { useChatPageController } from './useChatPageController'

export default function ChatPage() {
  const chat = useChatPageController()

  return (
    <Flex gap={16} style={{ height: 'calc(100vh - 154px)', minHeight: 560 }}>
      <SessionSidebar
        sessions={chat.sessions}
        activeSessionId={chat.activeSessionId}
        loadingSessions={chat.loadingSessions}
        editingSessionId={chat.editingSessionId}
        editingTitle={chat.editingTitle}
        mutatingSessionId={chat.mutatingSessionId}
        onStartNewSession={chat.startNewSession}
        onLoadSession={(sessionId) => void chat.loadSession(sessionId)}
        onStartEditingSession={chat.startEditingSession}
        onEditingTitleChange={chat.setEditingTitle}
        onCancelEditingSession={chat.cancelEditingSession}
        onSaveSessionTitle={(sessionId) => void chat.saveSessionTitle(sessionId)}
        onDeleteSession={(sessionId) => void chat.deleteSession(sessionId)}
      />

      <Flex vertical flex={1} style={{ minWidth: 0 }}>
        <Flex align="center" justify="space-between" gap={12} style={{ marginBottom: 12 }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            {chat.activeSession?.title ?? '新对话'}
          </Typography.Title>
          <Flex align="center" gap={8}>
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
        </Flex>

        <TranscriptPanel
          transcriptRef={chat.transcriptRef}
          messages={chat.messages}
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
          streaming={chat.streaming}
          onInputChange={chat.setInput}
          onSendMessage={() => void chat.sendMessage()}
          onStopStreaming={chat.stopStreaming}
        />
      </Flex>

      <ShareSessionModal
        open={chat.shareModalOpen}
        loading={chat.sharing}
        share={chat.activeShare}
        messages={chat.messages}
        onClose={chat.closeShareModal}
      />
    </Flex>
  )
}
