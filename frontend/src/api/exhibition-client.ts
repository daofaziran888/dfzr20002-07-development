/** 跨模块会展引擎 API：执行历史、配额视图、进度推进、施工待办与验收办理等。 */
import { request } from './client'
import type {
  CheckDetail,
  ExhibitionHistory,
  QuotaSummary,
  DAGStatus,
  HandoverResult,
  TodoResult,
  VoucherDetail,
  VoucherIssueResult,
} from '@/data/exhibition-types'

const EXHIBITION_BASE = '/api/exhibition'

/** 动作接口成功返回 {ok,...}，失败时 FastAPI 抛 {detail}。统一成 ok/reason。 */
async function mutationResult<T extends { ok?: boolean; reason?: string }>(
  response: Response,
): Promise<T> {
  const payload = (await response.json().catch(() => ({}))) as Record<string, unknown>
  if (!response.ok) {
    return {
      ok: false,
      reason: String(payload.detail ?? payload.reason ?? `接口返回 ${response.status}`),
      ...payload,
    } as unknown as T
  }
  return payload as unknown as T
}

export async function fetchBoothHistory(boothNo: string): Promise<ExhibitionHistory> {
  const response = await request(`${EXHIBITION_BASE}/${boothNo}/history`)
  if (!response.ok) throw new Error('执行历史查询失败')
  return await response.json()
}

export async function advanceConstructionNode(nodeId: number): Promise<{ ok: boolean; reason: string }> {
  const response = await request(`${EXHIBITION_BASE}/advance/${nodeId}`, { method: 'POST' })
  return await response.json()
}

export async function fetchQuotaSummary(): Promise<QuotaSummary> {
  const response = await request(`${EXHIBITION_BASE}/quota`)
  if (!response.ok) throw new Error('配额数据读取失败')
  return await response.json()
}

export async function signoffChecklist(checklistId: number): Promise<{ ok: boolean; reason: string }> {
  const response = await request(`${EXHIBITION_BASE}/checklist/${checklistId}/signoff`, { method: 'POST' })
  return await response.json()
}

export async function confirmHandover(handoverId: number): Promise<HandoverResult> {
  const response = await request(`${EXHIBITION_BASE}/handover/${handoverId}/confirm`, { method: 'POST' })
  return await response.json()
}

export async function issueChangeOrder(changeId: number): Promise<{ ok: boolean; reason: string }> {
  const response = await request(`${EXHIBITION_BASE}/change/${changeId}/issue`, { method: 'POST' })
  return await response.json()
}

export async function fetchSafetyStatus(boothNo: string): Promise<{ ok: boolean; reason: string }> {
  const response = await request(`${EXHIBITION_BASE}/safety/${boothNo}`)
  return await response.json()
}

export async function fetchDAGStatus(): Promise<DAGStatus> {
  const response = await request(`${EXHIBITION_BASE}/dag/validate`)
  return await response.json()
}

export async function fetchScheduleConflicts(): Promise<{ conflicts: Record<string, unknown>[]; count: number }> {
  const response = await request(`${EXHIBITION_BASE}/conflicts`)
  return await response.json()
}

// ---------- 施工待办（按依赖阻塞定位） ----------

export async function fetchConstructionTodos(params: {
  blocked_by?: string
  booth_no?: string
  node_name?: string
  keyword?: string
} = {}): Promise<TodoResult> {
  const query = new URLSearchParams(
    Object.fromEntries(Object.entries(params).filter(([, v]) => v)),
  ).toString()
  const response = await request(`${EXHIBITION_BASE}/construction/todos?${query}`)
  if (!response.ok) throw new Error('施工待办读取失败')
  return await response.json()
}

export async function fetchTodoSources(boothNo?: string): Promise<{
  sources: { source: string; count: number }[]
  total: number
}> {
  const query = boothNo ? `?booth_no=${encodeURIComponent(boothNo)}` : ''
  const response = await request(`${EXHIBITION_BASE}/construction/todos/sources${query}`)
  if (!response.ok) throw new Error('阻塞源读取失败')
  return await response.json()
}

// ---------- 前置检查 ----------

export async function fetchCheckDetail(checkNo: string): Promise<CheckDetail> {
  const response = await request(`${EXHIBITION_BASE}/checks/${encodeURIComponent(checkNo)}`)
  if (!response.ok) throw new Error('检查记录读取失败')
  return await response.json()
}

export async function recordCheckResult(
  checkNo: string,
  payload: { passed: boolean; conclusion?: string; operator?: string },
): Promise<{ ok: boolean; reason: string }> {
  const response = await request(`${EXHIBITION_BASE}/checks/${encodeURIComponent(checkNo)}/result`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return await mutationResult<{ ok: boolean; reason: string }>(response)
}

export async function reopenCheck(
  checkNo: string,
  payload: { reason?: string; change_id?: number } = {},
): Promise<{ ok: boolean; reason: string; new_check_no?: string }> {
  const response = await request(`${EXHIBITION_BASE}/checks/${encodeURIComponent(checkNo)}/reopen`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return await mutationResult<{ ok: boolean; reason: string; new_check_no?: string }>(response)
}

// ---------- 验收办理凭据 ----------

export async function issueVoucher(
  checklistId: number,
  payload: { node_id?: number; check_no?: string } = {},
): Promise<VoucherIssueResult> {
  const response = await request(`${EXHIBITION_BASE}/checklist/${checklistId}/voucher`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return await mutationResult<VoucherIssueResult>(response)
}

export async function fetchVoucher(voucherNo: string): Promise<VoucherDetail> {
  const response = await request(`${EXHIBITION_BASE}/vouchers/${encodeURIComponent(voucherNo)}`)
  if (!response.ok) throw new Error('办理凭据读取失败')
  return await response.json()
}

export async function submitVoucher(
  voucherNo: string,
  payload: { check_no?: string; remark?: string } = {},
): Promise<{ ok: boolean; reason: string; result_pending?: boolean }> {
  const response = await request(`${EXHIBITION_BASE}/vouchers/${encodeURIComponent(voucherNo)}/submit`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return await mutationResult<{ ok: boolean; reason: string; result_pending?: boolean }>(response)
}

export async function credentialSignoff(
  checklistId: number,
  payload: { voucher_no?: string; check_no?: string; node_id?: number } = {},
): Promise<{ ok: boolean; reason: string; invalid_credential?: boolean }> {
  const response = await request(`${EXHIBITION_BASE}/checklist/${checklistId}/credential-signoff`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return await mutationResult<{ ok: boolean; reason: string; invalid_credential?: boolean }>(response)
}