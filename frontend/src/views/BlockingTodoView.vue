<template>
  <section class="page" data-page="blocking-todos">
    <header class="page-head">
      <div>
        <h2>施工待办与验收办理</h2>
        <p class="page-desc">
          按依赖阻塞定位施工待办（前置节点 / 电检 / 安全巡检），同名节点按展位分别判断；
          验收员凭当前有效的电检结论拿到办理编号并提交签收。
        </p>
      </div>
    </header>

    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>

    <!-- 待办筛选 -->
    <form class="filter-bar" @submit.prevent="loadTodos">
      <label class="filter-item">
        <span>展位编号</span>
        <input v-model="todoBooth" placeholder="如 BOOT-A01" data-testid="todo-booth" />
      </label>
      <label class="filter-item">
        <span>阻塞源</span>
        <select v-model="todoBlockedBy" data-testid="todo-blocked-by">
          <option value="">全部阻塞源</option>
          <option v-for="source in availableSources" :key="source" :value="source">
            {{ source }}（{{ sourceCount(source) }}）
          </option>
        </select>
      </label>
      <button class="btn primary" data-testid="query-todos" type="submit">筛选待办</button>
    </form>

    <section class="card">
      <h4>施工待办（{{ todos.total }} 条，筛选：{{ todos.applied_filter }}）</h4>
      <table class="data-table">
        <thead>
          <tr>
            <th>展位</th>
            <th>节点名称</th>
            <th>节点状态</th>
            <th>阻塞源</th>
            <th>阻塞原因</th>
            <th>关联检查</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in todos.items"
            :key="`${item.booth_no}-${item.node_id}`"
            :data-testid="`todo-${item.booth_no}-${item.node_id}`"
          >
            <td>{{ item.booth_no }}</td>
            <td>{{ item['节点名称'] }}</td>
            <td>{{ item.status }}</td>
            <td>
              <span v-for="source in item.blocking_sources" :key="source" class="tag">{{ source }}</span>
            </td>
            <td>
              <div v-for="(blocker, idx) in item.blockers" :key="idx" class="blocker-line">
                {{ blocker.reason }}
                <button
                  v-if="blocker.check_no"
                  class="link"
                  type="button"
                  :data-testid="`open-check-${blocker.check_no}`"
                  @click="openCheck(blocker.check_no)"
                >
                  查看检查 {{ blocker.check_no }}
                </button>
              </div>
            </td>
            <td>
              <span v-for="check in item.related_checks" :key="check['检查编号']" class="check-chip">
                {{ check['检查编号'] }}（第{{ check['轮次'] }}轮/{{ check.status }}）
              </span>
            </td>
          </tr>
          <tr v-if="!todos.items.length">
            <td colspan="6" class="empty-state">当前筛选下没有施工待办</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 前置检查回看 -->
    <section class="card">
      <h4>前置检查回看</h4>
      <form class="filter-bar" @submit.prevent="openCheck(checkNo)">
        <label class="filter-item">
          <span>检查编号</span>
          <input v-model="checkNo" placeholder="如 ELEC-CHK-0002" data-testid="check-no-input" />
        </label>
        <button class="btn" data-testid="open-check" type="submit">按检查号回看</button>
      </form>

      <div v-if="checkDetail" data-testid="check-detail">
        <p>
          检查 <strong>{{ checkDetail.check_no }}</strong>
          <span :class="checkDetail.is_current ? 'text-success' : 'text-danger'">
            {{ checkDetail.is_current ? '当前有效' : '已作废（结论仍可回看）' }}
          </span>
          <span v-if="checkDetail.superseded_by" class="muted">
            → 已重开为 {{ checkDetail.superseded_by }}
          </span>
        </p>
        <table class="data-table">
          <thead>
            <tr><th>轮次</th><th>检查编号</th><th>状态</th><th>结论</th><th>说明</th></tr>
          </thead>
          <tbody>
            <tr v-for="round in checkDetail.history" :key="round['检查编号']">
              <td>第 {{ round['轮次'] }} 轮</td>
              <td>{{ round['检查编号'] }}</td>
              <td>{{ round.status }}</td>
              <td>{{ round.status === '已作废' ? (round['原结论'] || round['结论']) : round['结论'] }}</td>
              <td>{{ round['作废原因'] || round['重开原因'] || '—' }}</td>
            </tr>
          </tbody>
        </table>

        <div class="page-actions">
          <button class="btn" data-testid="record-pass" type="button" @click="recordResult(true)">
            录入：电检通过
          </button>
          <button class="btn" data-testid="record-fail" type="button" @click="recordResult(false)">
            录入：电检未通过
          </button>
          <button class="btn ghost" data-testid="reopen-check" type="button" @click="reopenCurrentCheck">
            重开检查（新开一轮待检）
          </button>
        </div>
        <p v-if="checkActionMessage" :class="checkActionOk ? 'text-success' : 'text-danger'" data-testid="check-action-message">
          {{ checkActionMessage }}
        </p>
      </div>
      <p v-else class="empty-state">输入检查编号回看该轮筛查结论（已作废的旧轮次同样可查）</p>
    </section>

    <!-- 验收办理 -->
    <section class="card">
      <h4>验收办理凭据</h4>
      <form class="filter-bar" @submit.prevent="openVoucher(voucherNo)">
        <label class="filter-item">
          <span>办理编号</span>
          <input v-model="voucherNo" placeholder="如 ACCP-0001" data-testid="voucher-no-input" />
        </label>
        <button class="btn" data-testid="open-voucher" type="submit">重新打开办理</button>
      </form>

      <form class="filter-bar" @submit.prevent="issueNewVoucher">
        <label class="filter-item">
          <span>验收项ID</span>
          <input v-model.number="issueChecklistId" type="number" min="1" data-testid="issue-checklist-id" />
        </label>
        <label class="filter-item">
          <span>进度节点ID</span>
          <input v-model.number="issueNodeId" type="number" min="1" data-testid="issue-node-id" />
        </label>
        <label class="filter-item">
          <span>检查编号</span>
          <input v-model="issueCheckNo" placeholder="留空则自动取当前已通过检查" data-testid="issue-check-no" />
        </label>
        <button class="btn primary" data-testid="issue-voucher" type="submit">签发办理凭据</button>
      </form>

      <p v-if="issueMessage" class="muted" data-testid="issue-message">{{ issueMessage }}</p>

      <div v-if="voucher" data-testid="voucher-detail">
        <p>
          办理 <strong>{{ voucher.voucher_no }}</strong>
          状态：{{ voucher.status }} / {{ voucher.signoff_status }}
          <span :class="voucher.can_complete ? 'text-success' : 'text-danger'">
            {{ voucher.can_complete ? '可以完成' : '暂不能完成' }}
          </span>
          <span v-if="voucher.needs_supplementary_check" class="text-danger">
            （需补检查）
          </span>
        </p>
        <p>
          原检查：{{ voucher.old_check_no }} →
          当前检查：{{ voucher.current_check_no || '无' }}
          | 同名节点变化：
          <span :class="voucher.same_name_nodes_changed ? 'text-danger' : 'text-success'">
            {{ voucher.same_name_nodes_changed ? '有变化' : '无变化' }}
          </span>
        </p>

        <h5>同一次签收的电检结论（{{ voucher.check_conclusion_count }} 份）</h5>
        <table class="data-table">
          <thead>
            <tr><th>轮次</th><th>检查编号</th><th>状态</th><th>结论</th><th>是否当前</th></tr>
          </thead>
          <tbody>
            <tr v-for="c in voucher.check_conclusions" :key="c.check_no">
              <td>第 {{ c.round }} 轮</td>
              <td>{{ c.check_no }}</td>
              <td>{{ c.status }}</td>
              <td>{{ c.conclusion }}</td>
              <td>{{ c.is_current ? '当前' : '旧结论' }}</td>
            </tr>
          </tbody>
        </table>

        <h5>A02 的同名节点变化</h5>
        <table class="data-table">
          <thead>
            <tr><th>展位</th><th>节点ID</th><th>状态（原→现）</th><th>检查</th><th>结论</th></tr>
          </thead>
          <tbody>
            <tr v-for="peer in voucher.same_name_nodes" :key="peer.booth_no">
              <td>{{ peer.booth_no }}</td>
              <td>{{ peer.node_id }}</td>
              <td>{{ peer.previous_status || '—' }} → {{ peer.status }}</td>
              <td>{{ peer.check_no }}（第{{ peer.check_round }}轮/{{ peer.check_status }}）</td>
              <td>{{ peer.reason }}</td>
            </tr>
            <tr v-if="!voucher.same_name_nodes.length">
              <td colspan="5" class="empty-state">没有其它展位的同名节点</td>
            </tr>
          </tbody>
        </table>

        <h5>不能完成的原因</h5>
        <ul>
          <li v-for="(blocker, idx) in voucher.completion_blockers" :key="idx">
            [{{ blocker.source }}] {{ blocker.reason }}
          </li>
          <li v-if="!voucher.completion_blockers.length" class="text-success">无阻塞，可以完成签收</li>
        </ul>

        <div class="page-actions">
          <button
            class="btn"
            data-testid="submit-voucher"
            type="button"
            :disabled="voucher.status === '已作废' || voucher.status === '已完成'"
            @click="submitCurrentVoucher"
          >
            提交签收
          </button>
          <button
            class="btn primary"
            data-testid="complete-voucher"
            type="button"
            :disabled="!voucher.can_complete"
            @click="completeCurrentVoucher"
          >
            完成签收
          </button>
          <button
            class="btn ghost"
            data-testid="signoff-old-check"
            type="button"
            @click="tryOldCheck"
          >
            用旧检查编号发起签收
          </button>
        </div>
        <p v-if="actionMessage" :class="actionOk ? 'text-success' : 'text-danger'" data-testid="action-message">
          {{ actionMessage }}
        </p>
      </div>
      <p v-else class="empty-state">输入办理编号重新打开，或为验收项签发新的办理凭据</p>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

import {
  credentialSignoff,
  fetchCheckDetail,
  fetchConstructionTodos,
  fetchTodoSources,
  fetchVoucher,
  issueVoucher,
  recordCheckResult,
  reopenCheck,
  submitVoucher,
} from '@/api/exhibition-client'
import type { CheckDetail, TodoResult, VoucherDetail } from '@/data/exhibition-types'

const todoBooth = ref('BOOT-A01')
const todoBlockedBy = ref('电检')
const todos = ref<TodoResult>({
  items: [],
  total: 0,
  booth_no: '',
  blocked_by: '',
  applied_filter: '全部',
  sources: [],
  available_sources: ['前置节点', '电检', '安全巡检'],
})
const sourceCounts = ref<{ source: string; count: number }[]>([])
const errorMessage = ref('')

const checkNo = ref('ELEC-CHK-0002')
const checkDetail = ref<CheckDetail | null>(null)
const checkActionMessage = ref('')
const checkActionOk = ref(false)

const voucherNo = ref('ACCP-0001')
const voucher = ref<VoucherDetail | null>(null)
const issueChecklistId = ref<number>(2)
const issueNodeId = ref<number>(3)
const issueCheckNo = ref('')
const issueMessage = ref('')
const actionMessage = ref('')
const actionOk = ref(false)

const availableSources = computed(() =>
  todos.value.available_sources.length
    ? todos.value.available_sources
    : ['前置节点', '电检', '安全巡检'],
)

function sourceCount(source: string): number {
  return sourceCounts.value.find((s) => s.source === source)?.count ?? 0
}

async function loadSources() {
  try {
    const result = await fetchTodoSources(todoBooth.value || undefined)
    sourceCounts.value = result.sources
  } catch {
    sourceCounts.value = []
  }
}

async function loadTodos() {
  errorMessage.value = ''
  try {
    todos.value = await fetchConstructionTodos({
      booth_no: todoBooth.value || undefined,
      blocked_by: todoBlockedBy.value || undefined,
    })
    await loadSources()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '施工待办读取失败'
  }
}

async function openCheck(value: string) {
  if (!value) return
  errorMessage.value = ''
  checkActionMessage.value = ''
  try {
    checkDetail.value = await fetchCheckDetail(value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检查回看失败'
  }
}

async function recordResult(passed: boolean) {
  if (!checkDetail.value) return
  checkActionMessage.value = ''
  const result = await recordCheckResult(checkDetail.value.check_no, {
    passed,
    conclusion: passed ? '复核通过' : '复核未通过',
  })
  checkActionOk.value = result.ok
  checkActionMessage.value = result.reason
  await openCheck(checkDetail.value.check_no)
  await loadTodos()
}

async function reopenCurrentCheck() {
  if (!checkDetail.value) return
  checkActionMessage.value = ''
  const result = await reopenCheck(checkDetail.value.check_no, { reason: '手工重开' })
  checkActionOk.value = result.ok
  checkActionMessage.value = result.ok
    ? `${result.reason}；旧结论已保留可回看`
    : result.reason
  await openCheck(checkDetail.value.check_no)
  await loadTodos()
}

async function openVoucher(value: string) {
  if (!value) return
  errorMessage.value = ''
  actionMessage.value = ''
  try {
    voucher.value = await fetchVoucher(value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '办理凭据读取失败'
  }
}

async function issueNewVoucher() {
  issueMessage.value = ''
  actionMessage.value = ''
  try {
    const result = await issueVoucher(issueChecklistId.value, {
      node_id: issueNodeId.value || undefined,
      check_no: issueCheckNo.value || undefined,
    })
    if (!result.ok) {
      issueMessage.value = result.reason
      return
    }
    issueMessage.value = result.reason
    voucherNo.value = result.voucher_no
    await openVoucher(result.voucher_no)
    await loadTodos()
  } catch (error) {
    issueMessage.value = error instanceof Error ? error.message : '签发失败'
  }
}

async function submitCurrentVoucher() {
  if (!voucher.value) return
  actionMessage.value = ''
  const result = await submitVoucher(voucher.value.voucher_no)
  actionOk.value = result.ok
  actionMessage.value = result.reason
  await openVoucher(voucher.value.voucher_no)
}

async function completeCurrentVoucher() {
  if (!voucher.value) return
  actionMessage.value = ''
  const checklistId = Number(voucher.value.voucher['验收项ID'])
  const result = await credentialSignoff(checklistId, { voucher_no: voucher.value.voucher_no })
  actionOk.value = result.ok
  actionMessage.value = result.reason
  await openVoucher(voucher.value.voucher_no)
  await loadTodos()
}

async function tryOldCheck() {
  if (!voucher.value) return
  actionMessage.value = ''
  const checklistId = Number(voucher.value.voucher['验收项ID'])
  const result = await credentialSignoff(checklistId, { check_no: voucher.value.old_check_no })
  actionOk.value = result.ok
  actionMessage.value = result.ok
    ? result.reason
    : `已拦住无效的电检凭据：${result.reason}`
}

loadTodos()
</script>

<style scoped>
.card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
  margin-bottom: 16px;
}
.card h4 { margin: 0 0 10px; }
.card h5 { margin: 14px 0 6px; font-size: 13px; color: #333; }
.tag {
  display: inline-block;
  padding: 1px 8px;
  margin-right: 6px;
  border-radius: 10px;
  background: #fff7e6;
  color: #d46b08;
  font-size: 12px;
}
.check-chip {
  display: inline-block;
  padding: 1px 6px;
  margin: 2px 4px 2px 0;
  border-radius: 4px;
  background: #e8f4ff;
  color: #1890ff;
  font-size: 12px;
}
.blocker-line { margin-bottom: 4px; }
.muted { color: var(--muted); font-size: 12px; }
.text-success { color: #52c41a; }
.text-danger { color: #f5222d; }
</style>
