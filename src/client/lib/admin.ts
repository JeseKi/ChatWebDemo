import api, { buildTwoFactorHeaders } from './api'
import type {
  AdminScope,
  AdminScopeUpdatePayload,
  AdminUser,
  AdminUserBulkDeletePayload,
  AdminUserBulkUpdatePayload,
  AdminUserCreatePayload,
  AdminUserScopesUpdatePayload,
  AdminUserUpdatePayload,
  TokenAuditBreakdown,
  TokenAuditBreakdownDimension,
  TokenAuditEventsResponse,
  TokenAuditQuery,
  TokenAuditSummary,
  TokenAuditTimeseriesGroupBy,
  TokenAuditTimeseriesPoint,
} from './types'

export async function createUser(
  payload: AdminUserCreatePayload,
  twoFactorCode?: string,
): Promise<AdminUser> {
  const { data } = await api.post<AdminUser>('/admin/users', payload, {
    headers: buildTwoFactorHeaders(twoFactorCode),
  })
  return data
}

export async function listUsers(): Promise<AdminUser[]> {
  const { data } = await api.get<AdminUser[]>('/admin/users')
  return data
}

export async function updateUser(
  userId: number,
  payload: AdminUserUpdatePayload,
  twoFactorCode?: string,
): Promise<AdminUser> {
  const { data } = await api.patch<AdminUser>(`/admin/users/${userId}`, payload, {
    headers: buildTwoFactorHeaders(twoFactorCode),
  })
  return data
}

export async function deleteUser(userId: number, twoFactorCode?: string): Promise<void> {
  await api.delete(`/admin/users/${userId}`, {
    headers: buildTwoFactorHeaders(twoFactorCode),
  })
}

export async function bulkUpdateUsers(
  payload: AdminUserBulkUpdatePayload,
  twoFactorCode?: string,
): Promise<AdminUser[]> {
  const { data } = await api.patch<AdminUser[]>('/admin/users/bulk', payload, {
    headers: buildTwoFactorHeaders(twoFactorCode),
  })
  return data
}

export async function bulkDeleteUsers(
  payload: AdminUserBulkDeletePayload,
  twoFactorCode?: string,
): Promise<void> {
  await api.delete('/admin/users/bulk', {
    data: payload,
    headers: buildTwoFactorHeaders(twoFactorCode),
  })
}

export async function listScopes(): Promise<AdminScope[]> {
  const { data } = await api.get<AdminScope[]>('/admin/scopes')
  return data
}

export async function updateScope(
  scope: string,
  payload: AdminScopeUpdatePayload,
  twoFactorCode?: string,
): Promise<AdminScope> {
  const { data } = await api.patch<AdminScope>(`/admin/scopes/${encodeURIComponent(scope)}`, payload, {
    headers: buildTwoFactorHeaders(twoFactorCode),
  })
  return data
}

export async function updateUserScopes(
  userId: number,
  payload: AdminUserScopesUpdatePayload,
  twoFactorCode?: string,
): Promise<AdminUser> {
  const { data } = await api.put<AdminUser>(`/admin/users/${userId}/scopes`, payload, {
    headers: buildTwoFactorHeaders(twoFactorCode),
  })
  return data
}

export async function listTokenAuditSummary(
  query: TokenAuditQuery = {},
): Promise<TokenAuditSummary[]> {
  const { data } = await api.get<TokenAuditSummary[]>('/admin/token-audit/summary', {
    params: query,
  })
  return data
}

export async function listTokenAuditEvents(
  query: TokenAuditQuery = {},
): Promise<TokenAuditEventsResponse> {
  const { data } = await api.get<TokenAuditEventsResponse>('/admin/token-audit/events', {
    params: query,
  })
  return data
}

export async function listTokenAuditTimeseries(
  query: TokenAuditQuery = {},
  groupBy: TokenAuditTimeseriesGroupBy = 'day',
): Promise<TokenAuditTimeseriesPoint[]> {
  const { data } = await api.get<TokenAuditTimeseriesPoint[]>('/admin/token-audit/timeseries', {
    params: { ...query, group_by: groupBy },
  })
  return data
}

export async function listTokenAuditBreakdown(
  query: TokenAuditQuery = {},
  dimension: TokenAuditBreakdownDimension,
  limit = 20,
): Promise<TokenAuditBreakdown[]> {
  const { data } = await api.get<TokenAuditBreakdown[]>('/admin/token-audit/breakdown', {
    params: { ...query, dimension, limit },
  })
  return data
}
