import { Alert, Form, Input, Modal, Space } from 'antd'
import type { FormInstance } from 'antd'
import type { AdminUser } from '../../../lib/types'

interface DeleteUserModalProps {
  open: boolean
  deletingUser: AdminUser | null
  deletingUsers?: AdminUser[]
  deleting: boolean
  form: FormInstance
  onOk: () => void
  onCancel: () => void
}

export default function DeleteUserModal({
  open,
  deletingUser,
  deletingUsers = [],
  deleting,
  form,
  onOk,
  onCancel,
}: DeleteUserModalProps) {
  const targetUsers = deletingUsers.length > 0 ? deletingUsers : deletingUser ? [deletingUser] : []
  const isBulkDelete = targetUsers.length > 1
  const usernamePreview = targetUsers.slice(0, 5).map((user) => user.username).join('、')
  const overflowCount = Math.max(targetUsers.length - 5, 0)

  return (
    <Modal
      title={
        isBulkDelete
          ? `批量删除 ${targetUsers.length} 个用户`
          : deletingUser ? `删除用户：${deletingUser.username}` : '删除用户'
      }
      open={open}
      onCancel={onCancel}
      onOk={onOk}
      okText="确认删除"
      okButtonProps={{ danger: true }}
      confirmLoading={deleting}
      destroyOnClose
      width={520}
    >
      <Space
        direction="vertical"
        size={16}
        style={{ width: '100%' }}
      >
        <Alert
          type="warning"
          showIcon
          message={isBulkDelete ? '删除后所选用户将无法继续登录。' : '删除后该用户将无法继续登录。'}
          description={
            isBulkDelete
              ? `请确认要删除 ${targetUsers.length} 个用户：${usernamePreview}${overflowCount > 0 ? ` 等 ${overflowCount} 个` : ''}。该操作不可撤销。`
              : deletingUser
              ? `请确认要删除用户 ${deletingUser.username}（${deletingUser.email}）。该操作不可撤销。`
              : '该操作不可撤销。'
          }
        />
        <Form
          form={form}
          layout="vertical"
          requiredMark={false}
        >
          <Form.Item
            label='输入"确认删除"'
            name="confirmationText"
            rules={[
              { required: true, message: '请输入确认文本' },
              {
                validator(_, value) {
                  if (typeof value === 'string' && value.trim() === '确认删除') {
                    return Promise.resolve()
                  }
                  return Promise.reject(new Error('请输入准确的"确认删除"'))
                },
              },
            ]}
          >
            <Input placeholder="请输入确认删除" />
          </Form.Item>
        </Form>
      </Space>
    </Modal>
  )
}
