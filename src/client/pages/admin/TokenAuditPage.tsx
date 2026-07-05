import { Alert, App, Button, Card, DatePicker, Flex, Input, Select, Space, Statistic, Table, Typography } from 'antd'
import { BarChartOutlined, ReloadOutlined } from '@ant-design/icons'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import type { Dayjs } from 'dayjs'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { listTokenAuditEvents, listTokenAuditSummary, listUsers } from '../../lib/admin'
import type { AdminUser, TokenAuditEvent, TokenAuditQuery, TokenAuditSummary } from '../../lib/types'

const { RangePicker } = DatePicker

const providerOptions = [
  { label: 'OpenAI Chat', value: 'openai_chat' },
  { label: 'OpenAI Responses', value: 'openai_responses' },
  { label: 'Anthropic', value: 'anthropic' },
  { label: 'Google', value: 'google' },
  { label: 'DeepSeek', value: 'deepseek' },
]

function formatNumber(value: number): string {
  return new Intl.NumberFormat().format(value)
}

export default function TokenAuditPage() {
  const { message } = App.useApp()
  const [users, setUsers] = useState<AdminUser[]>([])
  const [summary, setSummary] = useState<TokenAuditSummary[]>([])
  const [events, setEvents] = useState<TokenAuditEvent[]>([])
  const [totalEvents, setTotalEvents] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [userId, setUserId] = useState<number | undefined>()
  const [provider, setProvider] = useState<string | undefined>()
  const [modelId, setModelId] = useState('')
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null)
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20 })

  useEffect(() => {
    void listUsers().then(setUsers).catch(() => setUsers([]))
  }, [])

  const query = useCallback((page: number, pageSize: number): TokenAuditQuery => {
    const trimmedModel = modelId.trim()
    return {
      user_id: userId,
      provider,
      model_id: trimmedModel || undefined,
      start_at: range?.[0]?.startOf('day').toISOString(),
      end_at: range?.[1]?.endOf('day').toISOString(),
      limit: pageSize,
      offset: (page - 1) * pageSize,
    }
  }, [modelId, provider, range, userId])

  const loadData = useCallback(async (page: number, pageSize: number) => {
    setLoading(true)
    setError(null)
    try {
      const requestQuery = query(page, pageSize)
      const [summaryData, eventData] = await Promise.all([
        listTokenAuditSummary(requestQuery),
        listTokenAuditEvents(requestQuery),
      ])
      setSummary(summaryData)
      setEvents(eventData.items)
      setTotalEvents(eventData.total)
      setPagination({ current: page, pageSize })
    } catch (err) {
      const text = err instanceof Error ? err.message : 'Token 审计数据加载失败'
      setError(text)
      message.error(text)
    } finally {
      setLoading(false)
    }
  }, [message, query])

  useEffect(() => {
    void loadData(1, pagination.pageSize)
  }, [loadData, pagination.pageSize])

  const totals = useMemo(() => summary.reduce((acc, item) => ({
    request_count: acc.request_count + item.request_count,
    input_tokens: acc.input_tokens + item.input_tokens,
    output_tokens: acc.output_tokens + item.output_tokens,
    total_tokens: acc.total_tokens + item.total_tokens,
    reasoning_tokens: acc.reasoning_tokens + item.reasoning_tokens,
  }), {
    request_count: 0,
    input_tokens: 0,
    output_tokens: 0,
    total_tokens: 0,
    reasoning_tokens: 0,
  }), [summary])

  const userOptions = useMemo(() => users.map((user) => ({
    label: `${user.username} (${user.email})`,
    value: user.id,
  })), [users])

  const summaryColumns: ColumnsType<TokenAuditSummary> = [
    {
      title: '用户',
      key: 'user',
      render: (_, record) => (
        <Flex vertical>
          <Typography.Text strong>{record.username}</Typography.Text>
          <Typography.Text type="secondary">{record.email}</Typography.Text>
        </Flex>
      ),
    },
    { title: '请求数', dataIndex: 'request_count', render: formatNumber, sorter: (a, b) => a.request_count - b.request_count },
    { title: '输入', dataIndex: 'input_tokens', render: formatNumber, sorter: (a, b) => a.input_tokens - b.input_tokens },
    { title: '输出', dataIndex: 'output_tokens', render: formatNumber, sorter: (a, b) => a.output_tokens - b.output_tokens },
    { title: '推理', dataIndex: 'reasoning_tokens', render: formatNumber, sorter: (a, b) => a.reasoning_tokens - b.reasoning_tokens },
    { title: '总计', dataIndex: 'total_tokens', render: formatNumber, sorter: (a, b) => a.total_tokens - b.total_tokens, defaultSortOrder: 'descend' },
  ]

  const eventColumns: ColumnsType<TokenAuditEvent> = [
    { title: '时间', dataIndex: 'created_at', render: (value: string) => new Date(value).toLocaleString() },
    { title: '用户', dataIndex: 'username', render: (value: string | null, record) => value ?? `#${record.user_id}` },
    { title: '供应商', dataIndex: 'provider' },
    { title: '模型', dataIndex: 'model_id' },
    { title: '输入', dataIndex: 'input_tokens', render: formatNumber },
    { title: '输出', dataIndex: 'output_tokens', render: formatNumber },
    { title: '推理', dataIndex: 'reasoning_tokens', render: formatNumber },
    { title: '总计', dataIndex: 'total_tokens', render: formatNumber },
  ]

  const handleTableChange = (next: TablePaginationConfig) => {
    void loadData(next.current ?? 1, next.pageSize ?? pagination.pageSize)
  }

  return (
    <Flex vertical gap={24}>
      <Card>
        <Flex align="center" justify="space-between" wrap="wrap" gap={16}>
          <Space>
            <BarChartOutlined style={{ fontSize: 20 }} />
            <Typography.Title level={4} style={{ margin: 0 }}>Token 审计</Typography.Title>
          </Space>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => loadData(1, pagination.pageSize)}>
            刷新
          </Button>
        </Flex>
        <Flex wrap="wrap" gap={12} style={{ marginTop: 16 }}>
          <Select
            allowClear
            showSearch
            placeholder="用户"
            value={userId}
            options={userOptions}
            optionFilterProp="label"
            onChange={setUserId}
            style={{ minWidth: 240 }}
          />
          <Select
            allowClear
            placeholder="供应商"
            value={provider}
            options={providerOptions}
            onChange={setProvider}
            style={{ minWidth: 180 }}
          />
          <Input
            allowClear
            placeholder="模型 ID"
            value={modelId}
            onChange={(event) => setModelId(event.target.value)}
            style={{ width: 220 }}
          />
          <RangePicker value={range} onChange={(value) => setRange(value as [Dayjs, Dayjs] | null)} />
          <Button type="primary" loading={loading} onClick={() => loadData(1, pagination.pageSize)}>
            查询
          </Button>
        </Flex>
      </Card>

      {error && <Alert type="error" showIcon message={error} />}

      <Flex wrap="wrap" gap={16}>
        <Card style={{ minWidth: 180, flex: 1 }}>
          <Statistic title="总 Token" value={totals.total_tokens} formatter={(value) => formatNumber(Number(value))} />
        </Card>
        <Card style={{ minWidth: 180, flex: 1 }}>
          <Statistic title="输入 Token" value={totals.input_tokens} formatter={(value) => formatNumber(Number(value))} />
        </Card>
        <Card style={{ minWidth: 180, flex: 1 }}>
          <Statistic title="输出 Token" value={totals.output_tokens} formatter={(value) => formatNumber(Number(value))} />
        </Card>
        <Card style={{ minWidth: 180, flex: 1 }}>
          <Statistic title="请求数" value={totals.request_count} formatter={(value) => formatNumber(Number(value))} />
        </Card>
      </Flex>

      <Card title="用户汇总" bodyStyle={{ padding: 0 }}>
        <Table
          rowKey="user_id"
          columns={summaryColumns}
          dataSource={summary}
          loading={loading}
          pagination={false}
          scroll={{ x: 760 }}
        />
      </Card>

      <Card title="请求明细" bodyStyle={{ padding: 0 }}>
        <Table
          rowKey="id"
          columns={eventColumns}
          dataSource={events}
          loading={loading}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: totalEvents,
            showSizeChanger: true,
          }}
          onChange={handleTableChange}
          scroll={{ x: 980 }}
        />
      </Card>
    </Flex>
  )
}
