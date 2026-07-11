import {
  Button,
  Checkbox,
  Divider,
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
  ArrowLeftOutlined,
  CheckOutlined,
  CloseOutlined,
  DeleteOutlined,
  EditOutlined,
  MessageOutlined,
} from '@ant-design/icons'
import { Link } from 'react-router-dom'
import type { ChatSession } from '../../../lib/chat'

export default function SessionSidebar({
  sessions,
  selectedSessionIds,
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
  onDeleteSessions,
  onToggleSessionSelection,
  onSelectAllSessions,
  onClose,
}: {
  sessions: ChatSession[]
  selectedSessionIds: string[]
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
  onDeleteSessions: (sessionIds: string[]) => void
  onToggleSessionSelection: (sessionId: string) => void
  onSelectAllSessions: (selected: boolean) => void
  onClose: () => void
}) {
  return (
    <Flex
      vertical
      style={{
        width: '100%',
        minWidth: 0,
        height: '100%',
      }}
    >
      <Flex align="center" justify="space-between" gap={8} style={{ marginBottom: 12 }}>
        <Tooltip title="返回工作台">
          <Link to="/dashboard" onClick={onClose}>
            <Button type="text" icon={<ArrowLeftOutlined />} />
          </Link>
        </Tooltip>
        <Typography.Title level={5} style={{ margin: 0 }}>
          对话
        </Typography.Title>
        <Tooltip title="关闭侧栏">
          <Button type="text" icon={<CloseOutlined />} onClick={onClose} />
        </Tooltip>
      </Flex>
      <Button
        block
        icon={<EditOutlined />}
        onClick={onStartNewSession}
        style={{
          height: 40,
          justifyContent: 'flex-start',
          borderRadius: 8,
          fontWeight: 500,
        }}
      >
        新聊天
      </Button>
      <Divider style={{ margin: '12px 0' }} />
      {sessions.length > 0 && (
        <Flex align="center" justify="space-between" style={{ marginBottom: 8 }}>
          <Checkbox
            checked={selectedSessionIds.length === sessions.length}
            indeterminate={selectedSessionIds.length > 0 && selectedSessionIds.length < sessions.length}
            onChange={(event) => onSelectAllSessions(event.target.checked)}
          >
            全选
          </Checkbox>
          {selectedSessionIds.length > 0 && (
            <Popconfirm
              title="批量删除会话"
              description={`确定删除选中的 ${selectedSessionIds.length} 个会话吗？`}
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
              onConfirm={() => onDeleteSessions(selectedSessionIds)}
            >
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                loading={mutatingSessionId === 'bulk'}
              >
                删除所选 ({selectedSessionIds.length})
              </Button>
            </Popconfirm>
          )}
        </Flex>
      )}
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
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
                selected={selectedSessionIds.includes(session.id)}
                onToggleSessionSelection={onToggleSessionSelection}
              />
            )}
          />
        </Spin>
      </div>
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
  selected,
  onToggleSessionSelection,
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
  selected: boolean
  onToggleSessionSelection: (sessionId: string) => void
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
        avatar={
          <Flex align="center" gap={6} onClick={(event) => event.stopPropagation()}>
            <Checkbox
              checked={selected}
              onChange={() => onToggleSessionSelection(session.id)}
            />
            <MessageOutlined style={{ color: token.colorPrimary }} />
          </Flex>
        }
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
