import {
  Alert,
  App,
  Button,
  Card,
  DatePicker,
  Descriptions,
  Drawer,
  Empty,
  Flex,
  Input,
  Select,
  Segmented,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import {
  BarChartOutlined,
  DatabaseOutlined,
  EyeOutlined,
  LineChartOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import dayjs from 'dayjs'
import type { Dayjs } from 'dayjs'
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import {
  listTokenAuditBreakdown,
  listTokenAuditEvents,
  listTokenAuditSummary,
  listTokenAuditTimeseries,
  listUsers,
} from '../../lib/admin'
import type {
  AdminUser,
  TokenAuditBreakdown,
  TokenAuditEvent,
  TokenAuditQuery,
  TokenAuditSummary,
  TokenAuditTimeseriesGroupBy,
  TokenAuditTimeseriesPoint,
} from '../../lib/types'

const { RangePicker } = DatePicker

const providerOptions = [
  { label: 'OpenAI Chat', value: 'openai_chat' },
  { label: 'OpenAI Responses', value: 'openai_responses' },
  { label: 'Anthropic', value: 'anthropic' },
  { label: 'Google', value: 'google' },
  { label: 'DeepSeek', value: 'deepseek' },
]

const providerLabels = new Map(providerOptions.map((option) => [option.value, option.label]))

const tokenColors = {
  input: '#1677ff',
  output: '#16a34a',
  reasoning: '#f97316',
  cached: '#0891b2',
  tool: '#7c3aed',
}

type TokenSegmentKey = 'input' | 'output' | 'reasoning' | 'cached' | 'tool'

interface TokenAggregate {
  input_tokens: number
  output_tokens: number
  total_tokens: number
  reasoning_tokens: number
  cached_input_tokens: number
  tool_tokens: number
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat().format(value)
}

function formatCompact(value: number): string {
  return new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`
}

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString()
}

function resolveProviderLabel(value: string): string {
  return providerLabels.get(value) ?? value
}

function polarToCartesian(centerX: number, centerY: number, radius: number, angleInDegrees: number) {
  const angleInRadians = ((angleInDegrees - 90) * Math.PI) / 180
  return {
    x: centerX + radius * Math.cos(angleInRadians),
    y: centerY + radius * Math.sin(angleInRadians),
  }
}

function donutSegmentPath(
  centerX: number,
  centerY: number,
  outerRadius: number,
  innerRadius: number,
  startAngle: number,
  endAngle: number,
) {
  const outerStart = polarToCartesian(centerX, centerY, outerRadius, endAngle)
  const outerEnd = polarToCartesian(centerX, centerY, outerRadius, startAngle)
  const innerStart = polarToCartesian(centerX, centerY, innerRadius, startAngle)
  const innerEnd = polarToCartesian(centerX, centerY, innerRadius, endAngle)
  const largeArcFlag = endAngle - startAngle <= 180 ? '0' : '1'

  return [
    'M', outerStart.x, outerStart.y,
    'A', outerRadius, outerRadius, 0, largeArcFlag, 0, outerEnd.x, outerEnd.y,
    'L', innerStart.x, innerStart.y,
    'A', innerRadius, innerRadius, 0, largeArcFlag, 1, innerEnd.x, innerEnd.y,
    'Z',
  ].join(' ')
}

function tokenSegments(record: TokenAggregate) {
  return [
    { key: 'input' as const, label: '输入', value: record.input_tokens, color: tokenColors.input },
    { key: 'output' as const, label: '输出', value: record.output_tokens, color: tokenColors.output },
    { key: 'reasoning' as const, label: '推理', value: record.reasoning_tokens, color: tokenColors.reasoning },
    { key: 'tool' as const, label: '工具', value: record.tool_tokens, color: tokenColors.tool },
  ].filter((item) => item.value > 0)
}

function TokenCompositionBar({ record }: { record: TokenAggregate }) {
  const segments = tokenSegments(record)
  const total = segments.reduce((sum, item) => sum + item.value, 0)
  if (total <= 0) {
    return <Typography.Text type="secondary">-</Typography.Text>
  }

  return (
    <Tooltip
      title={segments.map((item) => `${item.label}: ${formatNumber(item.value)}`).join(' / ')}
    >
      <div style={{ display: 'flex', width: 150, height: 8, overflow: 'hidden', borderRadius: 6, background: 'var(--app-surface-muted)' }}>
        {segments.map((item) => (
          <span
            key={item.key}
            className="token-audit-composition-segment"
            style={{
              width: `${Math.max((item.value / total) * 100, 3)}%`,
              background: item.color,
            }}
          />
        ))}
      </div>
    </Tooltip>
  )
}

function ChartCard({
  title,
  extra,
  children,
}: {
  title: string
  extra?: ReactNode
  children: ReactNode
}) {
  return (
    <Card
      title={<Typography.Text strong>{title}</Typography.Text>}
      extra={extra}
      style={{ minHeight: 320 }}
    >
      {children}
    </Card>
  )
}

function TokenTrendChart({
  data,
  groupBy,
}: {
  data: TokenAuditTimeseriesPoint[]
  groupBy: TokenAuditTimeseriesGroupBy
}) {
  const width = 760
  const height = 220
  const padding = { top: 16, right: 20, bottom: 34, left: 42 }
  const chartWidth = width - padding.left - padding.right
  const chartHeight = height - padding.top - padding.bottom
  const series: { key: TokenSegmentKey; label: string; color: string }[] = [
    { key: 'input', label: '输入', color: tokenColors.input },
    { key: 'output', label: '输出', color: tokenColors.output },
    { key: 'reasoning', label: '推理', color: tokenColors.reasoning },
    { key: 'tool', label: '工具', color: tokenColors.tool },
  ]

  const points = data.map((item) => ({
    bucket: item.bucket_start,
    input: item.input_tokens,
    output: item.output_tokens,
    reasoning: item.reasoning_tokens,
    cached: item.cached_input_tokens,
    tool: item.tool_tokens,
    stackedTotal: item.input_tokens + item.output_tokens + item.reasoning_tokens + item.tool_tokens,
  }))
  const maxValue = Math.max(1, ...points.map((item) => Math.max(item.stackedTotal, item.cached)))
  const xForIndex = (index: number) => padding.left + (points.length === 1 ? chartWidth / 2 : (index / (points.length - 1)) * chartWidth)
  const yForValue = (value: number) => padding.top + chartHeight - (value / maxValue) * chartHeight

  if (points.length === 0) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无趋势数据" />
  }

  const layerPolygons: { key: TokenSegmentKey; label: string; color: string; points: string }[] = []
  const bottoms = points.map(() => 0)
  for (const item of series) {
    const tops = points.map((point, index) => {
      const value = bottoms[index] + point[item.key]
      return { x: xForIndex(index), y: yForValue(value), bottom: bottoms[index] }
    })
    const bottomPoints = points
      .map((_, index) => ({ x: xForIndex(index), y: yForValue(tops[index].bottom) }))
      .reverse()
    layerPolygons.push({
      ...item,
      points: [...tops, ...bottomPoints].map((point) => `${point.x},${point.y}`).join(' '),
    })
    points.forEach((point, index) => {
      bottoms[index] += point[item.key]
    })
  }

  const cachedLine = points.map((point, index) => `${xForIndex(index)},${yForValue(point.cached)}`).join(' ')
  const labelIndexes = points.length <= 3 ? points.map((_, index) => index) : [0, Math.floor((points.length - 1) / 2), points.length - 1]

  return (
    <Flex vertical gap={12}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Token 消耗趋势" style={{ width: '100%', height: 240 }}>
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const y = padding.top + chartHeight * ratio
          return (
            <line
              key={ratio}
              x1={padding.left}
              x2={width - padding.right}
              y1={y}
              y2={y}
              stroke="var(--app-border-color)"
              strokeDasharray="4 6"
            />
          )
        })}
        {layerPolygons.map((item) => (
          <polygon
            key={item.key}
            className="token-audit-trend-layer"
            points={item.points}
            fill={item.color}
            opacity={0.32}
          />
        ))}
        <polyline
          className="token-audit-trend-line"
          points={cachedLine}
          fill="none"
          stroke={tokenColors.cached}
          strokeWidth={2.5}
          strokeDasharray="6 5"
        />
        <text x={padding.left - 8} y={padding.top + 4} textAnchor="end" fill="var(--app-text-secondary)" fontSize="12">
          {formatCompact(maxValue)}
        </text>
        <text x={padding.left - 8} y={padding.top + chartHeight + 4} textAnchor="end" fill="var(--app-text-secondary)" fontSize="12">
          0
        </text>
        {labelIndexes.map((index) => (
          <text
            key={index}
            x={xForIndex(index)}
            y={height - 8}
            textAnchor={index === 0 ? 'start' : index === points.length - 1 ? 'end' : 'middle'}
            fill="var(--app-text-secondary)"
            fontSize="12"
          >
            {dayjs(points[index].bucket).format(groupBy === 'hour' ? 'MM-DD HH:mm' : 'MM-DD')}
          </text>
        ))}
      </svg>
      <Flex gap={12} wrap="wrap">
        {series.map((item) => (
          <LegendItem key={item.key} color={item.color} label={item.label} />
        ))}
        <LegendItem color={tokenColors.cached} label="缓存输入" dashed />
      </Flex>
    </Flex>
  )
}

function DonutChart({ data }: { data: TokenAuditBreakdown[] }) {
  const visible = data.filter((item) => item.total_tokens > 0)
  const total = visible.reduce((sum, item) => sum + item.total_tokens, 0)
  const colors = ['#1677ff', '#16a34a', '#f97316', '#7c3aed', '#0891b2', '#dc2626']
  const [hoveredKey, setHoveredKey] = useState<string | null>(null)

  if (visible.length === 0 || total <= 0) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无供应商数据" />
  }

  let cursor = 0
  const segments = visible.slice(0, 6).map((item, index) => {
    const startAngle = cursor
    const sweep = (item.total_tokens / total) * 359.99
    const endAngle = startAngle + sweep
    cursor = endAngle
    return {
      item,
      color: colors[index % colors.length],
      startAngle,
      endAngle,
      percent: item.total_tokens / total,
      path: donutSegmentPath(110, 110, 88, 54, startAngle, endAngle),
    }
  })
  const hoveredSegment = segments.find((segment) => segment.item.key === hoveredKey)
  const centerItem = hoveredSegment?.item

  return (
    <Flex align="center" gap={24} wrap="wrap">
      <svg
        viewBox="0 0 220 220"
        role="img"
        aria-label="供应商 token 占比"
        style={{ width: 190, height: 190, flex: 'none', overflow: 'visible' }}
        onMouseLeave={() => setHoveredKey(null)}
      >
        {segments.map((segment, index) => {
          const active = hoveredKey === null || hoveredKey === segment.item.key
          return (
            <path
              key={segment.item.key}
              className="token-audit-donut-segment"
              d={segment.path}
              fill={segment.color}
              opacity={active ? 1 : 0.38}
              style={{ animationDelay: `${index * 70}ms` }}
              onMouseEnter={() => setHoveredKey(segment.item.key)}
            >
              <title>
                {`${resolveProviderLabel(segment.item.label)}: ${formatNumber(segment.item.total_tokens)} Token (${formatPercent(segment.percent)})`}
              </title>
            </path>
          )
        })}
        <circle cx="110" cy="110" r="48" fill="var(--app-elevated-bg)" />
        <text x="110" y="98" textAnchor="middle" fill="var(--app-text-secondary)" fontSize="12">
          {centerItem ? resolveProviderLabel(centerItem.label) : '总计'}
        </text>
        <text x="110" y="120" textAnchor="middle" fill="var(--app-text-primary)" fontSize="18" fontWeight="700">
          {formatCompact(centerItem?.total_tokens ?? total)}
        </text>
        <text x="110" y="138" textAnchor="middle" fill="var(--app-text-secondary)" fontSize="12">
          {centerItem ? `${formatPercent((centerItem.total_tokens || 0) / total)} / ${formatNumber(centerItem.request_count)} 次` : 'Token'}
        </text>
      </svg>
      <Flex vertical gap={10} style={{ minWidth: 220, flex: 1 }}>
        {segments.map((segment) => (
          <Flex
            key={segment.item.key}
            className="token-audit-legend-row"
            justify="space-between"
            gap={12}
            onMouseEnter={() => setHoveredKey(segment.item.key)}
            onMouseLeave={() => setHoveredKey(null)}
            style={{ opacity: hoveredKey === null || hoveredKey === segment.item.key ? 1 : 0.48 }}
          >
            <LegendItem color={segment.color} label={resolveProviderLabel(segment.item.label)} />
            <Space size={10}>
              <Typography.Text type="secondary">{formatCompact(segment.item.total_tokens)}</Typography.Text>
              <Typography.Text strong>{formatPercent(segment.percent)}</Typography.Text>
            </Space>
          </Flex>
        ))}
      </Flex>
    </Flex>
  )
}

function RankingBars({
  data,
  emptyText,
  labelFormatter,
}: {
  data: TokenAuditBreakdown[]
  emptyText: string
  labelFormatter?: (item: TokenAuditBreakdown) => string
}) {
  const visible = data.filter((item) => item.total_tokens > 0).slice(0, 8)
  const maxValue = Math.max(1, ...visible.map((item) => item.total_tokens))
  if (visible.length === 0) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} />
  }

  return (
    <Flex vertical gap={14}>
      {visible.map((item) => (
        <div key={item.key}>
          <Flex justify="space-between" align="baseline" gap={12}>
            <Typography.Text ellipsis style={{ maxWidth: 280 }}>
              {labelFormatter ? labelFormatter(item) : item.label}
            </Typography.Text>
            <Typography.Text strong>{formatCompact(item.total_tokens)}</Typography.Text>
          </Flex>
          <div style={{ position: 'relative', height: 10, marginTop: 7, borderRadius: 8, overflow: 'hidden', background: 'var(--app-surface-muted)' }}>
            <div
              className="token-audit-ranking-bar"
              style={{
                width: `${Math.max((item.total_tokens / maxValue) * 100, 2)}%`,
                height: '100%',
                borderRadius: 8,
                background: 'linear-gradient(90deg, #1677ff, #16a34a 58%, #f97316)',
              }}
            />
          </div>
          <Flex gap={10} wrap="wrap" style={{ marginTop: 6 }}>
            <Typography.Text type="secondary">请求 {formatNumber(item.request_count)}</Typography.Text>
            <Typography.Text type="secondary">输入 {formatCompact(item.input_tokens)}</Typography.Text>
            <Typography.Text type="secondary">输出 {formatCompact(item.output_tokens)}</Typography.Text>
          </Flex>
        </div>
      ))}
    </Flex>
  )
}

function ModelCompositionBars({ data }: { data: TokenAuditBreakdown[] }) {
  const visible = data.filter((item) => item.total_tokens > 0).slice(0, 6)
  if (visible.length === 0) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无模型数据" />
  }

  return (
    <Flex vertical gap={14}>
      {visible.map((item) => (
        <div key={item.key}>
          <Flex justify="space-between" align="baseline" gap={12}>
            <Typography.Text code ellipsis style={{ maxWidth: 280 }}>{item.label}</Typography.Text>
            <Typography.Text strong>{formatCompact(item.total_tokens)}</Typography.Text>
          </Flex>
          <div style={{ marginTop: 8 }}>
            <TokenCompositionBar record={item} />
          </div>
        </div>
      ))}
      <Flex gap={12} wrap="wrap">
        <LegendItem color={tokenColors.input} label="输入" />
        <LegendItem color={tokenColors.output} label="输出" />
        <LegendItem color={tokenColors.reasoning} label="推理" />
        <LegendItem color={tokenColors.tool} label="工具" />
      </Flex>
    </Flex>
  )
}

function LegendItem({ color, label, dashed = false }: { color: string; label: string; dashed?: boolean }) {
  return (
    <Space size={6}>
      <span
        style={{
          width: 10,
          height: 10,
          borderRadius: 3,
          border: dashed ? `2px dashed ${color}` : undefined,
          background: dashed ? 'transparent' : color,
          display: 'inline-block',
        }}
      />
      <Typography.Text type="secondary">{label}</Typography.Text>
    </Space>
  )
}

export default function TokenAuditPage() {
  const { message } = App.useApp()
  const [users, setUsers] = useState<AdminUser[]>([])
  const [summary, setSummary] = useState<TokenAuditSummary[]>([])
  const [events, setEvents] = useState<TokenAuditEvent[]>([])
  const [timeseries, setTimeseries] = useState<TokenAuditTimeseriesPoint[]>([])
  const [providerBreakdown, setProviderBreakdown] = useState<TokenAuditBreakdown[]>([])
  const [userBreakdown, setUserBreakdown] = useState<TokenAuditBreakdown[]>([])
  const [modelBreakdown, setModelBreakdown] = useState<TokenAuditBreakdown[]>([])
  const [totalEvents, setTotalEvents] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [userId, setUserId] = useState<number | undefined>()
  const [provider, setProvider] = useState<string | undefined>()
  const [modelId, setModelId] = useState('')
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(() => [dayjs().subtract(6, 'day'), dayjs()])
  const [groupBy, setGroupBy] = useState<TokenAuditTimeseriesGroupBy>('day')
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20 })
  const [selectedEvent, setSelectedEvent] = useState<TokenAuditEvent | null>(null)

  useEffect(() => {
    void listUsers().then(setUsers).catch(() => setUsers([]))
  }, [])

  const query = useCallback((page?: number, pageSize?: number): TokenAuditQuery => {
    const trimmedModel = modelId.trim()
    return {
      user_id: userId,
      provider,
      model_id: trimmedModel || undefined,
      start_at: range?.[0]?.startOf('day').toISOString(),
      end_at: range?.[1]?.endOf('day').toISOString(),
      limit: pageSize,
      offset: page && pageSize ? (page - 1) * pageSize : undefined,
    }
  }, [modelId, provider, range, userId])

  const loadData = useCallback(async (page: number, pageSize: number) => {
    setLoading(true)
    setError(null)
    try {
      const requestQuery = query(page, pageSize)
      const aggregateQuery = query()
      const [
        summaryData,
        eventData,
        timeseriesData,
        providerData,
        userData,
        modelData,
      ] = await Promise.all([
        listTokenAuditSummary(aggregateQuery),
        listTokenAuditEvents(requestQuery),
        listTokenAuditTimeseries(aggregateQuery, groupBy),
        listTokenAuditBreakdown(aggregateQuery, 'provider', 8),
        listTokenAuditBreakdown(aggregateQuery, 'user', 8),
        listTokenAuditBreakdown(aggregateQuery, 'model', 8),
      ])
      setSummary(summaryData)
      setEvents(eventData.items)
      setTimeseries(timeseriesData)
      setProviderBreakdown(providerData)
      setUserBreakdown(userData)
      setModelBreakdown(modelData)
      setTotalEvents(eventData.total)
      setPagination({ current: page, pageSize })
    } catch (err) {
      const text = err instanceof Error ? err.message : 'Token 审计数据加载失败'
      setError(text)
      message.error(text)
    } finally {
      setLoading(false)
    }
  }, [groupBy, message, query])

  useEffect(() => {
    void loadData(1, pagination.pageSize)
  }, [loadData, pagination.pageSize])

  const totals = useMemo(() => summary.reduce((acc, item) => ({
    request_count: acc.request_count + item.request_count,
    input_tokens: acc.input_tokens + item.input_tokens,
    output_tokens: acc.output_tokens + item.output_tokens,
    total_tokens: acc.total_tokens + item.total_tokens,
    reasoning_tokens: acc.reasoning_tokens + item.reasoning_tokens,
    cached_input_tokens: acc.cached_input_tokens + item.cached_input_tokens,
    tool_tokens: acc.tool_tokens + item.tool_tokens,
  }), {
    request_count: 0,
    input_tokens: 0,
    output_tokens: 0,
    total_tokens: 0,
    reasoning_tokens: 0,
    cached_input_tokens: 0,
    tool_tokens: 0,
  }), [summary])

  const averageTokens = totals.request_count > 0 ? totals.total_tokens / totals.request_count : 0
  const cachedShare = totals.input_tokens > 0 ? totals.cached_input_tokens / totals.input_tokens : 0
  const reasoningShare = totals.total_tokens > 0 ? totals.reasoning_tokens / totals.total_tokens : 0
  const topModel = modelBreakdown[0]?.label ?? '-'
  const chartGridStyle: CSSProperties = {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 360px), 1fr))',
    gap: 16,
  }

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
          <Typography.Text strong>{record.name || record.username}</Typography.Text>
          <Typography.Text type="secondary">{record.email}</Typography.Text>
        </Flex>
      ),
    },
    { title: '请求数', dataIndex: 'request_count', render: formatNumber, sorter: (a, b) => a.request_count - b.request_count },
    { title: '输入', dataIndex: 'input_tokens', render: formatNumber, sorter: (a, b) => a.input_tokens - b.input_tokens },
    { title: '输出', dataIndex: 'output_tokens', render: formatNumber, sorter: (a, b) => a.output_tokens - b.output_tokens },
    { title: '推理', dataIndex: 'reasoning_tokens', render: formatNumber, sorter: (a, b) => a.reasoning_tokens - b.reasoning_tokens },
    { title: '缓存输入', dataIndex: 'cached_input_tokens', render: formatNumber, sorter: (a, b) => a.cached_input_tokens - b.cached_input_tokens },
    { title: '总计', dataIndex: 'total_tokens', render: formatNumber, sorter: (a, b) => a.total_tokens - b.total_tokens, defaultSortOrder: 'descend' },
  ]

  const eventColumns: ColumnsType<TokenAuditEvent> = [
    { title: '时间', dataIndex: 'created_at', render: formatDateTime },
    { title: '用户', dataIndex: 'username', render: (value: string | null, record) => value ?? `#${record.user_id}` },
    { title: '供应商', dataIndex: 'provider', render: resolveProviderLabel },
    { title: '模型', dataIndex: 'model_id', render: (value: string) => <Typography.Text code>{value}</Typography.Text> },
    { title: '构成', key: 'composition', render: (_, record) => <TokenCompositionBar record={record} /> },
    { title: '总计', dataIndex: 'total_tokens', render: formatNumber, sorter: (a, b) => a.total_tokens - b.total_tokens },
    {
      title: '详情',
      key: 'details',
      render: (_, record) => (
        <Button size="small" icon={<EyeOutlined />} onClick={() => setSelectedEvent(record)}>
          查看
        </Button>
      ),
    },
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
          <Space wrap>
            <Segmented<TokenAuditTimeseriesGroupBy>
              value={groupBy}
              options={[
                { label: '按天', value: 'day' },
                { label: '按小时', value: 'hour' },
              ]}
              onChange={setGroupBy}
            />
            <Button icon={<ReloadOutlined />} loading={loading} onClick={() => loadData(1, pagination.pageSize)}>
              刷新
            </Button>
          </Space>
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
          <Statistic title="总 Token" value={totals.total_tokens} formatter={(value) => formatNumber(Number(value))} prefix={<DatabaseOutlined />} />
        </Card>
        <Card style={{ minWidth: 180, flex: 1 }}>
          <Statistic title="请求数" value={totals.request_count} formatter={(value) => formatNumber(Number(value))} />
        </Card>
        <Card style={{ minWidth: 180, flex: 1 }}>
          <Statistic title="平均 / 请求" value={Math.round(averageTokens)} formatter={(value) => formatNumber(Number(value))} />
        </Card>
        <Card style={{ minWidth: 180, flex: 1 }}>
          <Statistic title="缓存输入占比" value={cachedShare} formatter={(value) => formatPercent(Number(value))} />
        </Card>
        <Card style={{ minWidth: 180, flex: 1 }}>
          <Statistic title="推理占比" value={reasoningShare} formatter={(value) => formatPercent(Number(value))} />
        </Card>
        <Card style={{ minWidth: 220, flex: 1 }}>
          <Statistic title="Top 模型" value={topModel} valueStyle={{ fontSize: 18 }} />
        </Card>
      </Flex>

      <div style={chartGridStyle}>
        <ChartCard
          title="Token 趋势"
          extra={<Tag icon={<LineChartOutlined />} color="blue">{groupBy === 'hour' ? '小时粒度' : '天粒度'}</Tag>}
        >
          <TokenTrendChart data={timeseries} groupBy={groupBy} />
        </ChartCard>
        <ChartCard title="供应商占比">
          <DonutChart data={providerBreakdown} />
        </ChartCard>
      </div>

      <div style={chartGridStyle}>
        <ChartCard title="Top 用户">
          <RankingBars
            data={userBreakdown}
            emptyText="暂无用户消耗数据"
            labelFormatter={(item) => item.username ? `${item.label} (${item.username})` : item.label}
          />
        </ChartCard>
        <ChartCard title="Top 模型构成">
          <ModelCompositionBars data={modelBreakdown} />
        </ChartCard>
      </div>

      <Card title="用户汇总" bodyStyle={{ padding: 0 }}>
        <Table
          rowKey="user_id"
          columns={summaryColumns}
          dataSource={summary}
          loading={loading}
          pagination={false}
          scroll={{ x: 920 }}
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

      <Drawer
        title="请求 Token 明细"
        open={Boolean(selectedEvent)}
        onClose={() => setSelectedEvent(null)}
        width={620}
      >
        {selectedEvent && (
          <Flex vertical gap={18}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="时间">{formatDateTime(selectedEvent.created_at)}</Descriptions.Item>
              <Descriptions.Item label="用户">{selectedEvent.username ?? `#${selectedEvent.user_id}`}</Descriptions.Item>
              <Descriptions.Item label="供应商">{resolveProviderLabel(selectedEvent.provider)}</Descriptions.Item>
              <Descriptions.Item label="模型"><Typography.Text code>{selectedEvent.model_id}</Typography.Text></Descriptions.Item>
              <Descriptions.Item label="Session ID"><Typography.Text code>{selectedEvent.session_id}</Typography.Text></Descriptions.Item>
              <Descriptions.Item label="Run ID"><Typography.Text code>{selectedEvent.run_id}</Typography.Text></Descriptions.Item>
              <Descriptions.Item label="请求序号">{selectedEvent.request_index}</Descriptions.Item>
            </Descriptions>
            <Flex wrap="wrap" gap={12}>
              <Tag color="blue">输入 {formatNumber(selectedEvent.input_tokens)}</Tag>
              <Tag color="green">输出 {formatNumber(selectedEvent.output_tokens)}</Tag>
              <Tag color="orange">推理 {formatNumber(selectedEvent.reasoning_tokens)}</Tag>
              <Tag color="cyan">缓存输入 {formatNumber(selectedEvent.cached_input_tokens)}</Tag>
              <Tag color="purple">工具 {formatNumber(selectedEvent.tool_tokens)}</Tag>
              <Tag>总计 {formatNumber(selectedEvent.total_tokens)}</Tag>
            </Flex>
            <Typography.Text strong>Raw Usage</Typography.Text>
            <pre
              style={{
                margin: 0,
                padding: 12,
                borderRadius: 8,
                overflow: 'auto',
                background: 'var(--app-surface-muted)',
                color: 'var(--app-text-primary)',
                fontSize: 12,
                lineHeight: 1.5,
              }}
            >
              {JSON.stringify(selectedEvent.raw_usage ?? {}, null, 2)}
            </pre>
          </Flex>
        )}
      </Drawer>
    </Flex>
  )
}
