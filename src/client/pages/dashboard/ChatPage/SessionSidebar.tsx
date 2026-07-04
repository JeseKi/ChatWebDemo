import {
  Button,
  Empty,
  Flex,
  Input,
  List,
  Popconfirm,
  Space,
  Spin,
  Tooltip,
  Typography,
  theme,
} from 'antd'
import {
  CheckOutlined,
  CloseOutlined,
  DeleteOutlined,
  EditOutlined,
  MessageOutlined,
  PlusOutlined,
} from '@ant-design/icons'
import type { ChatSession } from '../../../lib/chat'

export default function SessionSidebar({
  sessions,
  activeSessionId,
  loadingSessions,
  editingSessionId,
  editingTitle,
  mutatingSessionId,
  onStartNewSession,
  onLoadSession,
  onStartEditingSession,
  onEditingTitleChange,
  onCancelEditingSession,
  onSaveSessionTitle,
  onDeleteSession,
}: {
  sessions: ChatSession[]
  activeSessionId: string | null
  loadingSessions: boolean
  editingSessionId: string | null
  editingTitle: string
  mutatingSessionId: string | null
  onStartNewSession: () => void
  onLoadSession: (sessionId: string) => void
  onStartEditingSession: (session: ChatSession) => void
  onEditingTitleChange: (value: string) => void
  onCancelEditingSession: () => void
  onSaveSessionTitle: (sessionId: string) => void
  onDeleteSession: (sessionId: string) => void
}) {
  const { token } = theme.useToken()

  return (
    <Flex
      vertical
      style={{
        width: 280,
        minWidth: 220,
        borderRight: `1px solid ${token.colorBorder}`,
        paddingRight: 12,
      }}
    >
      <Flex align="center" justify="space-between" style={{ marginBottom: 12 }}>
        <Typography.Title level={5} style={{ margin: 0 }}>
          对话
        </Typography.Title>
        <Tooltip title="新对话">
          <Button icon={<PlusOutlined />} onClick={onStartNewSession} />
        </Tooltip>
      </Flex>
      <Spin spinning={loadingSessions}>
        <List
          dataSource={sessions}
          locale={{
            emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无对话" />,
          }}
          renderItem={(session) => (
            <SessionListItem
              session={session}
              activeSessionId={activeSessionId}
              editingSessionId={editingSessionId}
              editingTitle={editingTitle}
              mutatingSessionId={mutatingSessionId}
              onLoadSession={onLoadSession}
              onStartEditingSession={onStartEditingSession}
              onEditingTitleChange={onEditingTitleChange}
              onCancelEditingSession={onCancelEditingSession}
              onSaveSessionTitle={onSaveSessionTitle}
              onDeleteSession={onDeleteSession}
            />
          )}
        />
      </Spin>
    </Flex>
  )
}

function SessionListItem({
  session,
  activeSessionId,
  editingSessionId,
  editingTitle,
  mutatingSessionId,
  onLoadSession,
  onStartEditingSession,
  onEditingTitleChange,
  onCancelEditingSession,
  onSaveSessionTitle,
  onDeleteSession,
}: {
  session: ChatSession
  activeSessionId: string | null
  editingSessionId: string | null
  editingTitle: string
  mutatingSessionId: string | null
  onLoadSession: (sessionId: string) => void
  onStartEditingSession: (session: ChatSession) => void
  onEditingTitleChange: (value: string) => void
  onCancelEditingSession: () => void
  onSaveSessionTitle: (sessionId: string) => void
  onDeleteSession: (sessionId: string) => void
}) {
  const { token } = theme.useToken()

  return (
    <List.Item
      onClick={() => {
        if (editingSessionId !== session.id) {
          onLoadSession(session.id)
        }
      }}
      style={{
        cursor: 'pointer',
        paddingInline: 8,
        borderRadius: 6,
        background: session.id === activeSessionId ? token.colorPrimaryBg : 'transparent',
      }}
    >
      <List.Item.Meta
        avatar={<MessageOutlined style={{ color: token.colorPrimary }} />}
        title={
          editingSessionId === session.id ? (
            <SessionTitleEditor
              sessionId={session.id}
              editingTitle={editingTitle}
              loading={mutatingSessionId === session.id}
              onEditingTitleChange={onEditingTitleChange}
              onCancelEditingSession={onCancelEditingSession}
              onSaveSessionTitle={onSaveSessionTitle}
            />
          ) : (
            <SessionTitleView
              session={session}
              loading={mutatingSessionId === session.id}
              onStartEditingSession={onStartEditingSession}
              onDeleteSession={onDeleteSession}
            />
          )
        }
        description={new Date(session.updated_at).toLocaleString()}
      />
    </List.Item>
  )
}

function SessionTitleEditor({
  sessionId,
  editingTitle,
  loading,
  onEditingTitleChange,
  onCancelEditingSession,
  onSaveSessionTitle,
}: {
  sessionId: string
  editingTitle: string
  loading: boolean
  onEditingTitleChange: (value: string) => void
  onCancelEditingSession: () => void
  onSaveSessionTitle: (sessionId: string) => void
}) {
  return (
    <Flex gap={4} onClick={(event) => event.stopPropagation()}>
      <Input
        size="small"
        value={editingTitle}
        autoFocus
        maxLength={160}
        onChange={(event) => onEditingTitleChange(event.target.value)}
        onPressEnter={() => onSaveSessionTitle(sessionId)}
      />
      <Tooltip title="保存">
        <Button
          size="small"
          type="text"
          icon={<CheckOutlined />}
          loading={loading}
          onClick={() => onSaveSessionTitle(sessionId)}
        />
      </Tooltip>
      <Tooltip title="取消">
        <Button
          size="small"
          type="text"
          icon={<CloseOutlined />}
          onClick={onCancelEditingSession}
        />
      </Tooltip>
    </Flex>
  )
}

function SessionTitleView({
  session,
  loading,
  onStartEditingSession,
  onDeleteSession,
}: {
  session: ChatSession
  loading: boolean
  onStartEditingSession: (session: ChatSession) => void
  onDeleteSession: (sessionId: string) => void
}) {
  return (
    <Flex align="center" justify="space-between" gap={8}>
      <Typography.Text ellipsis style={{ flex: 1 }}>
        {session.title}
      </Typography.Text>
      <Space size={2} onClick={(event) => event.stopPropagation()}>
        <Tooltip title="重命名">
          <Button
            size="small"
            type="text"
            icon={<EditOutlined />}
            onClick={() => onStartEditingSession(session)}
          />
        </Tooltip>
        <Popconfirm
          title="删除会话"
          description="该会话和消息记录会被删除。"
          okText="删除"
          cancelText="取消"
          okButtonProps={{ danger: true }}
          onConfirm={() => onDeleteSession(session.id)}
        >
          <Tooltip title="删除">
            <Button
              size="small"
              type="text"
              danger
              icon={<DeleteOutlined />}
              loading={loading}
            />
          </Tooltip>
        </Popconfirm>
      </Space>
    </Flex>
  )
}
