/** 会展引擎专用类型 */

export interface EventRecord {
  id: number
  timestamp: number
  module: string
  entry_id: number
  action: string
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  extra: Record<string, unknown>
}

export interface SafetyStatus {
  ok: boolean
  reason: string
  total_inspections: number
  failed_inspections: Record<string, unknown>[]
}

export interface ElectricalQuota {
  booth_no: string
  design_load: number
  total_circuit_power: number
  over_draw: number
  circuits: Record<string, unknown>[]
}

export interface ExhibitionHistory {
  booth_no: string
  booth: Record<string, unknown> | null
  design: Record<string, unknown> | null
  events: EventRecord[]
  event_count: number
  current_safety: SafetyStatus
  current_electrical: { ok: boolean; reason: string; quota: ElectricalQuota }
  schedule_conflicts: Record<string, unknown>[]
}

export interface QuotaItem {
  venue: string
  venue_id: number
  ok: boolean
  reason: string
  quota: Record<string, unknown>
}

export interface PowerQuotaItem {
  ok: boolean
  reason: string
  quota: ElectricalQuota
}

export interface ScheduleConflict {
  transport_id: number
  exhibit: string
  arrival: string
  schedule_id: number
  event: string
  setup_start: string
  conflict: string
}

export interface QuotaSummary {
  area_quotas: QuotaItem[]
  power_quotas: PowerQuotaItem[]
  schedule_conflicts: ScheduleConflict[]
  schedule_conflict_count: number
  dag_cycle: string[] | null
  dag_ok: boolean
  overall_ok: boolean
}

export interface DAGStatus {
  cycle: string[] | null
  has_cycle: boolean
  topological_order: string[]
  node_count: number
}

export interface HandoverResult {
  ok: boolean
  reason: string
  handover?: Record<string, unknown>
  validation?: Record<string, unknown>
}

/** 施工待办：按依赖阻塞定位。 */
export interface Blocker {
  source: string
  reason: string
  check_no?: string
  check_round?: number
  check_status?: string
  predecessor?: string
  predecessor_status?: string
}

export interface ConstructionTodo {
  id: number
  node_id: number
  节点名称: string
  booth_no: string
  status: string
  blocked: boolean
  blocking_sources: string[]
  primary_source: string
  blockers: Blocker[]
  related_checks: PrerequisiteCheck[]
}

export interface TodoResult {
  items: ConstructionTodo[]
  total: number
  booth_no: string
  blocked_by: string
  applied_filter: string
  sources: { source: string; count: number }[]
  available_sources: string[]
}

export interface PrerequisiteCheck {
  id: number
  检查编号: string
  检查类型: string
  展位编号: string
  节点名称: string
  轮次: number
  结论: string
  status: string
  原检查编号?: string
  替代检查编号?: string
  原结论?: string
  作废原因?: string
  重开原因?: string
}

export interface CheckDetail {
  ok: boolean
  check_no: string
  check: PrerequisiteCheck
  is_current: boolean
  superseded_by: string | null
  current_check_no: string | null
  history: PrerequisiteCheck[]
  round_count: number
  conclusion_preserved: boolean
}

export interface CheckConclusion {
  check_no: string
  round: number
  status: string
  conclusion: string
  superseded: boolean
  reason: string
  is_current: boolean
}

export interface SameNameNode {
  booth_no: string
  node_id: number
  status: string
  check_no: string
  check_round: number | null
  check_status: string
  changed: boolean
  previous_status: string
  previous_check_no: string
  reason: string
}

export interface VoucherDetail {
  ok: boolean
  voucher_no: string
  voucher: Record<string, unknown>
  status: string
  signoff_status: string
  can_complete: boolean
  needs_supplementary_check: boolean
  completion_blockers: Blocker[]
  credential_valid: boolean
  old_check_no: string
  current_check_no: string | null
  check_conclusions: CheckConclusion[]
  check_conclusion_count: number
  two_conclusions: boolean
  same_name_nodes: SameNameNode[]
  same_name_nodes_changed: boolean
  related_change_orders: Record<string, unknown>[]
}

export interface VoucherIssueResult {
  ok: boolean
  reason: string
  voucher_no: string
  voucher: Record<string, unknown>
  reused: boolean
}