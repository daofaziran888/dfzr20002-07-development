"""施工待办、前置检查与验收办理凭据的领域逻辑。

本模块只依赖内存仓库，不反向引用 exhibition 引擎，避免循环导入；
exhibition 的变更传播在运行时调用这里重开前置检查、作废旧凭据。

核心规则：
1. 施工待办按阻塞源（前置节点 / 电检 / 安全巡检）筛选，同名节点按展位分别判断。
2. 前置检查每一轮有唯一检查编号；重开后旧编号保留结论供值班员回看，但状态作废。
3. 验收办理凭据只能从“当前轮次、已通过”的检查结论签发；
   旧轮次结论在重开后既不能签发新凭据，也不能用于新的签收。
4. 已提交的办理凭据被重开检查作废后，重新打开可以看到能否完成、是否需补检查，
   以及另一展位同名节点相对签发时是否发生变化。
"""
from __future__ import annotations

import copy
import time
from typing import Any

from app.store import store

# 阻塞源标准名称与常见别名，接口筛选时统一归一化。
BLOCK_SOURCE_ALIASES: dict[str, str] = {
    "电检": "电检",
    "电气": "电检",
    "用电": "电检",
    "electrical": "电检",
    "前置节点": "前置节点",
    "前置": "前置节点",
    "依赖": "前置节点",
    "dependency": "前置节点",
    "predecessor": "前置节点",
    "安全巡检": "安全巡检",
    "安全": "安全巡检",
    "巡检": "安全巡检",
    "safety": "安全巡检",
}

CHECK_TYPE_PREFIX = {"电检": "ELEC-CHK", "结构检查": "STRU-CHK", "安全巡检": "SAFE-CHK"}
CHECK_STATUS_PASSED = "已通过"
CHECK_STATUS_SUPERSEDED = "已作废"
VOUCHER_ACTIVE = ("待提交", "已提交")


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _booth_of_node(node: dict[str, Any]) -> str:
    """进度节点所属展位（备注说明的第一个空白片段）。"""
    remark = str(node.get("备注说明", "")).strip()
    return remark.split()[0] if remark else ""


def _normalize_source(value: str | None) -> str | None:
    if not value:
        return None
    raw = str(value).strip()
    return BLOCK_SOURCE_ALIASES.get(raw.casefold()) or BLOCK_SOURCE_ALIASES.get(raw) or raw


# ---------- 前置检查 ----------

def list_checks() -> list[dict[str, Any]]:
    return store.rows("prerequisite_check")


def find_check(check_no: str) -> dict[str, Any] | None:
    for check in list_checks():
        if str(check.get("检查编号", "")) == str(check_no):
            return check
    return None


def checks_for(
    booth_no: str | None = None,
    *,
    node_name: str | None = None,
    check_type: str | None = None,
    include_superseded: bool = False,
) -> list[dict[str, Any]]:
    rows = list_checks()
    if booth_no:
        rows = [r for r in rows if str(r.get("展位编号", "")) == booth_no]
    if node_name:
        rows = [r for r in rows if str(r.get("节点名称", "")) == node_name]
    if check_type:
        rows = [r for r in rows if str(r.get("检查类型", "")) == check_type]
    if not include_superseded:
        rows = [r for r in rows if str(r.get("status", "")) != CHECK_STATUS_SUPERSEDED]
    return sorted(rows, key=lambda r: (int(r.get("轮次") or 1), int(r.get("id") or 0)))


def current_check(
    booth_no: str, node_name: str, check_type: str | None = None
) -> dict[str, Any] | None:
    """当前有效轮次：同一展位、同一节点、同一检查类型里轮次最大的未作废一轮。"""
    rows = checks_for(booth_no, node_name=node_name, check_type=check_type)
    if not rows:
        return None
    return max(rows, key=lambda r: (int(r.get("轮次") or 1), int(r.get("id") or 0)))


def latest_round(booth_no: str, node_name: str, check_type: str) -> dict[str, Any] | None:
    """含已作废轮次在内的最大轮次。"""
    rows = checks_for(
        booth_no, node_name=node_name, check_type=check_type, include_superseded=True
    )
    if not rows:
        return None
    return max(rows, key=lambda r: (int(r.get("轮次") or 1), int(r.get("id") or 0)))


def _new_check_row(check_type: str) -> tuple[int, str]:
    """一次性分配 id 与检查编号，保证两者后半段一致。"""
    prefix = CHECK_TYPE_PREFIX.get(check_type, "PREC-CHK")
    for _ in range(1000):
        new_id = store.next_id("prerequisite_check")
        candidate = f"{prefix}-{new_id:04d}"
        if find_check(candidate) is None:
            return new_id, candidate
    new_id = store.next_id("prerequisite_check")
    return new_id, f"{prefix}-{new_id:04d}"


def check_history(booth_no: str, node_name: str, check_type: str) -> list[dict[str, Any]]:
    """同展位同节点同类型的所有轮次，按轮次正序，保留旧结论。"""
    rows = checks_for(
        booth_no, node_name=node_name, check_type=check_type, include_superseded=True
    )
    return sorted(rows, key=lambda r: int(r.get("轮次") or 1))


def check_detail(check_no: str) -> dict[str, Any]:
    """按检查号回看：即使该轮已作废，也返回它当初的筛查结论。"""
    check = find_check(check_no)
    if check is None:
        return {"ok": False, "reason": f"检查编号 {check_no} 不存在"}
    booth_no = str(check.get("展位编号", ""))
    node_name = str(check.get("节点名称", ""))
    check_type = str(check.get("检查类型", ""))
    history = check_history(booth_no, node_name, check_type)
    current = current_check(booth_no, node_name, check_type)
    return {
        "ok": True,
        "check_no": check_no,
        "check": check,
        "is_current": str(check.get("status", "")) != CHECK_STATUS_SUPERSEDED,
        "superseded_by": check.get("替代检查编号", "") or None,
        "current_check_no": current.get("检查编号") if current else None,
        "history": history,
        "round_count": len(history),
        "conclusion_preserved": bool(check.get("结论") or check.get("原结论")),
        "lookup_available": True,
    }


def _reopen_one(check: dict[str, Any], reason: str, change_id: int | None) -> dict[str, Any]:
    check_no = str(check.get("检查编号", ""))
    booth_no = str(check.get("展位编号", ""))
    node_name = str(check.get("节点名称", ""))
    check_type = str(check.get("检查类型", ""))
    round_no = int(check.get("轮次", 1))

    latest = latest_round(booth_no, node_name, check_type)
    if latest is not None and int(latest.get("轮次", 1)) > round_no:
        return {
            "ok": False,
            "reason": f"检查 {check_no} 已是旧轮次，当前轮次为 {latest.get('检查编号')}",
            "check_no": check_no,
            "current_check_no": latest.get("检查编号"),
        }

    new_id, new_check_no = _new_check_row(check_type)

    old_conclusion = str(check.get("结论", "")) or str(check.get("status", ""))
    before_state = copy.deepcopy(check)
    check["status"] = CHECK_STATUS_SUPERSEDED
    check["pending"] = False
    check["abnormal"] = False
    check["原结论"] = old_conclusion
    check["作废原因"] = reason or f"前置检查被重开，第 {round_no + 1} 轮待检"
    check["替代检查编号"] = new_check_no

    new_check: dict[str, Any] = {
        "id": new_id,
        "status": "待检",
        "pending": True,
        "abnormal": True,
        "检查编号": new_check_no,
        "检查类型": check_type,
        "展位编号": booth_no,
        "节点名称": node_name,
        "轮次": round_no + 1,
        "结论": "待检",
        "复查日期": check.get("复查日期", ""),
        "原检查编号": check_no,
        "重开原因": reason,
        "关联变更单": change_id or "",
        "登记编号": check.get("登记编号", ""),
        "负责人": check.get("负责人", ""),
        "生效版本": check.get("生效版本", ""),
        "备注说明": f"重开自 {check_no}，旧结论：{old_conclusion}",
    }
    list_checks().append(new_check)

    store.event_log.record(
        module="prerequisite_check",
        entry_id=int(check.get("id", 0)),
        action="重开前置检查",
        before=before_state,
        after=copy.deepcopy(check),
        extra={
            "booth_no": booth_no,
            "check_no": check_no,
            "new_check_no": new_check_no,
            "round": round_no + 1,
            "old_conclusion": old_conclusion,
            "reason": reason,
            "change_id": change_id,
        },
    )
    store.rebuild_indices()
    return {
        "ok": True,
        "check": new_check,
        "new_check_no": new_check_no,
        "new_check_id": new_id,
        "old_conclusion": old_conclusion,
    }


def _invalidate_vouchers_for_check(
    check_no: str, new_check_no: str, reason: str
) -> list[dict[str, Any]]:
    invalidated: list[dict[str, Any]] = []
    for voucher in store.rows("acceptance_voucher"):
        if str(voucher.get("检查编号", "")) != check_no:
            continue
        if str(voucher.get("status", "")) not in VOUCHER_ACTIVE + ("已完成",):
            continue
        before_state = copy.deepcopy(voucher)
        voucher["status"] = "已作废"
        voucher["签收状态"] = "已作废"
        voucher["pending"] = False
        voucher["abnormal"] = True
        voucher["作废原因"] = (
            reason or f"关联检查 {check_no} 已重开，原电检结论不能继续使用"
        )
        voucher["替代检查编号"] = new_check_no
        voucher["失效时间"] = _now()

        checklist_id = voucher.get("验收项ID")
        item = store.find("checklist", int(checklist_id)) if checklist_id is not None else None
        if item is not None and str(item.get("status", "")) == "已确认":
            item["status"] = "待确认"
            item["pending"] = True
            item["abnormal"] = True

        store.event_log.record(
            module="acceptance_voucher",
            entry_id=int(voucher.get("id", 0)),
            action="作废办理凭据",
            before=before_state,
            after=copy.deepcopy(voucher),
            extra={
                "booth_no": voucher.get("展位编号", ""),
                "voucher_no": voucher.get("办理编号", ""),
                "check_no": check_no,
                "new_check_no": new_check_no,
                "voucher_status": voucher["status"],
                "reason": voucher["作废原因"],
            },
        )
        invalidated.append(copy.deepcopy(voucher))
    if invalidated:
        store.rebuild_indices()
    return invalidated


def reopen_prerequisite_check(
    check_no: str, *, reason: str = "", change_id: int | None = None
) -> dict[str, Any]:
    """重开某一轮前置检查：新开一轮待检，旧轮结论保留但作废其签发的凭据。"""
    check = find_check(check_no)
    if check is None:
        return {"ok": False, "reason": f"检查编号 {check_no} 不存在"}

    if str(check.get("status", "")) == CHECK_STATUS_SUPERSEDED:
        return {
            "ok": False,
            "reason": (
                f"检查 {check_no} 已经作废，不能重复重开；"
                f"当前检查为 {check.get('替代检查编号', '未知')}"
            ),
            "check_no": check_no,
            "current_check_no": check.get("替代检查编号"),
        }

    reopened = _reopen_one(check, reason, change_id)
    if not reopened["ok"]:
        return reopened

    invalidated = _invalidate_vouchers_for_check(
        check_no,
        reopened["new_check_no"],
        reason or f"检查 {check_no} 已重开，原电检结论不能继续使用",
    )

    return {
        "ok": True,
        "reason": f"检查 {check_no} 已重开，新检查编号 {reopened['new_check_no']}",
        "check_no": check_no,
        "new_check_no": reopened["new_check_no"],
        "new_check": reopened["check"],
        "old_conclusion": reopened["old_conclusion"],
        "invalidated_vouchers": invalidated,
        "historical_check": check_detail(check_no),
    }


def reopen_checks_for_booth(
    booth_no: str,
    *,
    check_type: str = "电检",
    reason: str = "",
    change_id: int | None = None,
) -> dict[str, Any]:
    """变更传播：重开该展位当前所有指定类型的前置检查。"""
    current_rows = [
        c
        for c in checks_for(booth_no, check_type=check_type)
        if str(c.get("status", "")) != CHECK_STATUS_SUPERSEDED
    ]
    reopened: list[dict[str, Any]] = []
    invalidated: list[dict[str, Any]] = []
    for check in current_rows:
        result = reopen_prerequisite_check(
            str(check.get("检查编号", "")),
            reason=reason or f"变更单重开 {check_type}",
            change_id=change_id,
        )
        if result.get("ok"):
            reopened.append(
                {
                    "check_no": result["check_no"],
                    "new_check_no": result["new_check_no"],
                    "node_name": check.get("节点名称", ""),
                    "round": result["new_check"].get("轮次"),
                }
            )
            invalidated.extend(result.get("invalidated_vouchers", []))
    return {
        "booth_no": booth_no,
        "check_type": check_type,
        "reopened_checks": reopened,
        "invalidated_vouchers": invalidated,
        "reopened_count": len(reopened),
        "invalidated_count": len(invalidated),
    }


def validate_credential(
    check_no: str, *, booth_no: str | None = None, node_name: str | None = None
) -> dict[str, Any]:
    """校验检查号能否作为办理凭据：必须是当前轮次且已通过。"""
    check = find_check(check_no)
    if check is None:
        return {"ok": False, "reason": f"检查编号 {check_no} 不存在", "check_no": check_no}

    status = str(check.get("status", ""))
    if status == CHECK_STATUS_SUPERSEDED:
        return {
            "ok": False,
            "reason": (
                f"检查编号 {check_no} 已因重开作废（原结论："
                f"{check.get('原结论') or check.get('结论') or '无'}），不能作为办理凭据"
            ),
            "check_no": check_no,
            "superseded_by": check.get("替代检查编号"),
            "historical_conclusion": check.get("原结论") or check.get("结论"),
        }
    if status != CHECK_STATUS_PASSED:
        return {
            "ok": False,
            "reason": (
                f"检查编号 {check_no} 尚未通过（当前状态：{status}），"
                "不能签发或使用办理凭据"
            ),
            "check_no": check_no,
            "status": status,
        }
    if booth_no and str(check.get("展位编号", "")) != booth_no:
        return {
            "ok": False,
            "reason": (
                f"检查编号 {check_no} 属于展位 {check.get('展位编号', '')}，"
                f"与目标展位 {booth_no} 不一致"
            ),
            "check_no": check_no,
        }
    if node_name and str(check.get("节点名称", "")) != node_name:
        return {
            "ok": False,
            "reason": (
                f"检查编号 {check_no} 对应节点 {check.get('节点名称', '')}，"
                f"与目标节点 {node_name} 不一致"
            ),
            "check_no": check_no,
        }

    latest = latest_round(
        str(check.get("展位编号", "")),
        str(check.get("节点名称", "")),
        str(check.get("检查类型", "")),
    )
    if latest is not None and int(check.get("轮次", 1)) < int(latest.get("轮次", 1)):
        return {
            "ok": False,
            "reason": (
                f"检查编号 {check_no} 是第 {check.get('轮次')} 轮旧结论，"
                f"已被第 {latest.get('轮次')} 轮 {latest.get('检查编号')} 取代，"
                "不能作为办理凭据"
            ),
            "check_no": check_no,
            "current_check_no": latest.get("检查编号"),
        }

    return {
        "ok": True,
        "reason": "检查结论有效",
        "check_no": check_no,
        "check": check,
        "round": check.get("轮次"),
        "conclusion": check.get("结论"),
    }


# ---------- 施工待办 ----------

def _predecessor_blockers(
    node: dict[str, Any], scoped_nodes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    pred_text = str(node.get("前置节点", "")).strip()
    preds = [p.strip() for p in pred_text.split(",") if p.strip()]
    blockers: list[dict[str, Any]] = []
    for pred_name in preds:
        pred_node = next(
            (n for n in scoped_nodes if str(n.get("节点名称", "")) == pred_name), None
        )
        if pred_node is None:
            blockers.append(
                {
                    "source": "前置节点",
                    "predecessor": pred_name,
                    "reason": f"前置节点「{pred_name}」不存在或不属于本展位",
                }
            )
        elif str(pred_node.get("status", "")) != "已确认":
            blockers.append(
                {
                    "source": "前置节点",
                    "predecessor": pred_name,
                    "predecessor_id": pred_node.get("id"),
                    "predecessor_status": pred_node.get("status"),
                    "reason": (
                        f"前置节点「{pred_name}」当前状态为 "
                        f"{pred_node.get('status')}，未完成"
                    ),
                }
            )
    return blockers


def _check_blockers(node: dict[str, Any], booth_no: str) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    node_name = str(node.get("节点名称", ""))
    for check in checks_for(booth_no, node_name=node_name):
        status = str(check.get("status", ""))
        if status == CHECK_STATUS_PASSED:
            continue
        check_type = str(check.get("检查类型", "前置检查"))
        blockers.append(
            {
                "source": check_type,
                "check_no": check.get("检查编号"),
                "check_round": check.get("轮次"),
                "check_status": status,
                "conclusion": check.get("结论"),
                "reason": (
                    f"{check_type} {check.get('检查编号')} "
                    f"第 {check.get('轮次')} 轮未通过（{status}）"
                ),
            }
        )
    return blockers


def _safety_blockers(booth_no: str) -> list[dict[str, Any]]:
    inspections = store.booth_safety(booth_no)
    failed = [i for i in inspections if str(i.get("status", "")) != "已确认"]
    if not failed:
        return []
    points = "、".join(str(i.get("检查点位", "")) for i in failed)
    return [
        {
            "source": "安全巡检",
            "reason": f"展位 {booth_no} 有 {len(failed)} 条安全巡检未通过（{points}）",
            "inspections": [
                {"id": i.get("id"), "point": i.get("检查点位"), "status": i.get("status")}
                for i in failed
            ],
        }
    ]


def construction_todos(
    *,
    blocked_by: str | None = None,
    booth_no: str | None = None,
    node_name: str | None = None,
    keyword: str | None = None,
) -> dict[str, Any]:
    """按依赖阻塞定位施工待办，并可按阻塞源筛选。"""
    nodes = list(store.rows("construction"))
    if booth_no:
        nodes = [n for n in nodes if _booth_of_node(n) == booth_no]
    if node_name:
        nodes = [n for n in nodes if str(n.get("节点名称", "")) == node_name]
    if keyword:
        key = keyword.casefold()
        nodes = [
            n
            for n in nodes
            if key in str(n.get("节点名称", "")).casefold()
            or key in str(n.get("备注说明", "")).casefold()
        ]

    source_filter = _normalize_source(blocked_by)
    items: list[dict[str, Any]] = []
    source_counts: dict[str, int] = {}

    for node in nodes:
        node_booth = _booth_of_node(node)
        scoped_nodes = [
            n for n in store.rows("construction") if _booth_of_node(n) == node_booth
        ]
        blockers = (
            _predecessor_blockers(node, scoped_nodes)
            + _check_blockers(node, node_booth)
            + _safety_blockers(node_booth)
        )
        for blocker in blockers:
            source = str(blocker.get("source", ""))
            source_counts[source] = source_counts.get(source, 0) + 1

        is_confirmed = str(node.get("status", "")) == "已确认"
        if is_confirmed and not blockers:
            continue
        if source_filter:
            blockers = [
                b
                for b in blockers
                if _normalize_source(str(b.get("source", ""))) == source_filter
            ]
            if not blockers:
                continue

        sources = sorted({str(b.get("source", "")) for b in blockers})
        items.append(
            {
                "id": node.get("id"),
                "node_id": node.get("id"),
                "节点名称": node.get("节点名称", ""),
                "booth_no": node_booth,
                "status": node.get("status", ""),
                "计划日期": node.get("计划日期", ""),
                "完成日期": node.get("完成日期", ""),
                "前置节点": node.get("前置节点", ""),
                "负责人": node.get("负责人", ""),
                "登记编号": node.get("登记编号", ""),
                "blocked": bool(blockers),
                "blocking_sources": sources,
                "primary_source": sources[0] if sources else "无阻塞",
                "blockers": blockers,
                "related_checks": checks_for(
                    node_booth, node_name=str(node.get("节点名称", ""))
                ),
            }
        )

    return {
        "items": items,
        "total": len(items),
        "booth_no": booth_no or "",
        "node_name": node_name or "",
        "blocked_by": source_filter or "",
        "applied_filter": source_filter or "全部",
        "sources": [
            {"source": source, "count": count}
            for source, count in sorted(source_counts.items())
        ],
        "available_sources": ["前置节点", "电检", "安全巡检"],
    }


def todo_sources(*, booth_no: str | None = None) -> dict[str, Any]:
    result = construction_todos(booth_no=booth_no)
    return {
        "booth_no": booth_no or "",
        "sources": result["sources"],
        "total": result["total"],
    }


# ---------- 验收办理凭据 ----------

def _find_voucher(voucher_no: str) -> dict[str, Any] | None:
    for voucher in store.rows("acceptance_voucher"):
        if str(voucher.get("办理编号", "")) == str(voucher_no):
            return voucher
    return None


def _vouchers_for_checklist(checklist_id: int) -> list[dict[str, Any]]:
    return [
        v
        for v in store.rows("acceptance_voucher")
        if v.get("验收项ID") is not None and int(v.get("验收项ID")) == int(checklist_id)
    ]


def _peer_snapshot(node: dict[str, Any]) -> list[dict[str, Any]]:
    """记录其它展位同名节点的当前状态，用于重开前后比对。"""
    node_name = str(node.get("节点名称", ""))
    peers: list[dict[str, Any]] = []
    for other in store.rows("construction"):
        if _booth_of_node(other) == _booth_of_node(node):
            continue
        if str(other.get("节点名称", "")) != node_name:
            continue
        booth_no = _booth_of_node(other)
        check = current_check(booth_no, node_name)
        peers.append(
            {
                "booth_no": booth_no,
                "node_id": other.get("id"),
                "status": other.get("status", ""),
                "check_no": check.get("检查编号") if check else "",
                "check_round": check.get("轮次") if check else None,
                "check_status": check.get("status") if check else "",
            }
        )
    return peers


def _peers_changed(
    node: dict[str, Any], snapshot: list[dict[str, Any]]
) -> tuple[bool, list[dict[str, Any]]]:
    current = _peer_snapshot(node)
    changes: list[dict[str, Any]] = []
    for peer in current:
        old = next(
            (s for s in snapshot if str(s.get("booth_no")) == str(peer.get("booth_no"))),
            None,
        )
        if old is None:
            changes.append({**peer, "changed": True, "reason": "签发凭据时该同名节点尚不存在"})
            continue
        changed = (
            str(old.get("status", "")) != str(peer.get("status", ""))
            or int(old.get("check_round") or 0) != int(peer.get("check_round") or 0)
            or str(old.get("check_status", "")) != str(peer.get("check_status", ""))
        )
        if str(old.get("status", "")) != str(peer.get("status", "")):
            reason = f"同名节点状态由 {old.get('status')} 变为 {peer.get('status')}"
        elif changed:
            reason = "电检轮次/结论发生变化"
        else:
            reason = "无变化"
        changes.append(
            {
                **peer,
                "changed": changed,
                "previous_status": old.get("status", ""),
                "previous_check_no": old.get("check_no", ""),
                "previous_check_round": old.get("check_round"),
                "reason": reason,
            }
        )
    return any(c["changed"] for c in changes), changes


def issue_acceptance_voucher(
    checklist_id: int,
    *,
    node_id: int | None = None,
    check_no: str | None = None,
) -> dict[str, Any]:
    """从进度节点 + 当前有效的已通过前置检查签发验收办理凭据。"""
    item = store.find("checklist", checklist_id)
    if item is None:
        return {"ok": False, "reason": f"验收项 {checklist_id} 不存在"}
    booth_no = str(item.get("负责班组", "")).strip()
    if not booth_no:
        return {"ok": False, "reason": f"验收项 {checklist_id} 未登记负责班组"}

    node = store.find("construction", node_id) if node_id is not None else None
    if node_id is not None and node is None:
        return {"ok": False, "reason": f"进度节点 {node_id} 不存在"}

    if node is not None and _booth_of_node(node) != booth_no:
        return {
            "ok": False,
            "reason": (
                f"进度节点 {node.get('id')} 属于展位 {_booth_of_node(node)}，"
                f"与验收项展位 {booth_no} 不一致"
            ),
        }

    check: dict[str, Any] | None = None
    if check_no:
        check = find_check(check_no)
        if check is None:
            return {"ok": False, "reason": f"检查编号 {check_no} 不存在"}
        if str(check.get("展位编号", "")) != booth_no:
            return {
                "ok": False,
                "reason": (
                    f"检查 {check.get('检查编号')} 属于展位 "
                    f"{check.get('展位编号')}，与验收项展位 {booth_no} 不一致"
                ),
            }
    else:
        candidates = [
            c
            for c in checks_for(booth_no)
            if str(c.get("status", "")) == CHECK_STATUS_PASSED
            and (
                node is None
                or str(c.get("节点名称", "")) == str(node.get("节点名称", ""))
            )
        ]
        if candidates:
            check = max(
                candidates, key=lambda c: (int(c.get("轮次", 1)), int(c.get("id", 0)))
            )

    if check is None:
        return {
            "ok": False,
            "reason": f"展位 {booth_no} 没有可用的已通过前置检查，不能签发办理凭据",
        }

    target_node_name = (
        str(node.get("节点名称", ""))
        if node is not None
        else str(check.get("节点名称", ""))
    )
    credential = validate_credential(
        str(check.get("检查编号", "")), booth_no=booth_no, node_name=target_node_name
    )
    if not credential["ok"]:
        return {
            "ok": False,
            "reason": credential["reason"],
            "credential": credential,
            "check_no": check.get("检查编号"),
        }

    if node is None:
        node = next(
            (
                n
                for n in store.rows("construction")
                if _booth_of_node(n) == booth_no
                and str(n.get("节点名称", "")) == target_node_name
            ),
            None,
        )
    if node is None:
        return {
            "ok": False,
            "reason": (
                f"检查 {check.get('检查编号')} 对应的进度节点不属于展位 {booth_no}"
            ),
        }

    # 同一验收项 + 同一检查编号重复签发时返回已有有效凭据。
    existing = next(
        (
            v
            for v in _vouchers_for_checklist(checklist_id)
            if str(v.get("检查编号", "")) == str(check.get("检查编号"))
            and str(v.get("status", "")) in VOUCHER_ACTIVE + ("已完成",)
        ),
        None,
    )
    if existing is not None:
        return {
            "ok": True,
            "reason": f"办理凭据已存在：{existing.get('办理编号')}",
            "voucher_no": existing.get("办理编号"),
            "voucher": existing,
            "reused": True,
        }

    voucher_id = store.next_id("acceptance_voucher")
    voucher_no = f"ACCP-{voucher_id:04d}"
    snapshot = _peer_snapshot(node)
    voucher: dict[str, Any] = {
        "id": voucher_id,
        "status": "待提交",
        "pending": True,
        "abnormal": False,
        "办理编号": voucher_no,
        "验收项ID": checklist_id,
        "验收条目": item.get("验收条目", ""),
        "展位编号": booth_no,
        "进度节点ID": node.get("id"),
        "节点名称": node.get("节点名称", ""),
        "检查编号": check.get("检查编号"),
        "检查轮次": check.get("轮次"),
        "检查结论": check.get("结论"),
        "签收状态": "未提交",
        "结果": "待签收",
        "签发时间": _now(),
        "提交时间": "",
        "作废原因": "",
        "替代检查编号": "",
        "同类节点快照": snapshot,
        "备注说明": (
            f"由进度节点「{node.get('节点名称')}」+ 检查 "
            f"{check.get('检查编号')} 签发"
        ),
        "登记编号": item.get("登记编号", ""),
        "负责人": item.get("负责人", ""),
        "生效版本": item.get("生效版本", "v1.0"),
    }
    store.rows("acceptance_voucher").append(voucher)
    store.event_log.record(
        module="acceptance_voucher",
        entry_id=voucher_id,
        action="签发办理凭据",
        after=copy.deepcopy(voucher),
        extra={
            "booth_no": booth_no,
            "voucher_no": voucher_no,
            "checklist_id": checklist_id,
            "check_no": check.get("检查编号"),
            "node_id": node.get("id"),
            "node_name": node.get("节点名称"),
        },
    )
    store.rebuild_indices()
    return {
        "ok": True,
        "reason": f"已签发验收办理凭据 {voucher_no}",
        "voucher_no": voucher_no,
        "voucher": voucher,
        "reused": False,
        "credential": credential,
    }


def _voucher_completion(voucher: dict[str, Any]) -> dict[str, Any]:
    checklist_id = voucher.get("验收项ID")
    item = store.find("checklist", int(checklist_id)) if checklist_id is not None else None
    booth_no = str(voucher.get("展位编号", ""))
    node_name = str(voucher.get("节点名称", ""))
    node = (
        store.find("construction", int(voucher.get("进度节点ID")))
        if voucher.get("进度节点ID") is not None
        else None
    )

    credential = validate_credential(
        str(voucher.get("检查编号", "")), booth_no=booth_no, node_name=node_name
    )
    source_check = find_check(str(voucher.get("检查编号", "")))
    check_type = str(source_check.get("检查类型", "电检")) if source_check else "电检"
    current = current_check(booth_no, node_name, check_type)

    blockers: list[dict[str, Any]] = []
    if str(voucher.get("status", "")) == "已作废":
        blockers.append(
            {
                "source": "办理凭据",
                "reason": voucher.get("作废原因") or "办理凭据已作废",
            }
        )
    if not credential["ok"]:
        blockers.append({"source": "电检凭据", "reason": credential["reason"]})
    if item is None:
        blockers.append(
            {"source": "验收清单", "reason": f"验收项 {checklist_id} 不存在"}
        )
    elif str(item.get("status", "")) == "已确认":
        blockers.append(
            {
                "source": "验收清单",
                "reason": f"验收项 {item.get('验收条目', '')} 已签收完成",
            }
        )

    if node is not None:
        scoped = [
            n
            for n in store.rows("construction")
            if _booth_of_node(n) == _booth_of_node(node)
        ]
        node_blockers = _predecessor_blockers(node, scoped) + _check_blockers(node, booth_no)
        blockers.extend(node_blockers)
    else:
        blockers.append(
            {
                "source": "进度节点",
                "reason": f"进度节点 {voucher.get('进度节点ID')} 不存在",
            }
        )
    blockers.extend(_safety_blockers(booth_no))

    can_complete = (
        not blockers
        and str(voucher.get("status", "")) not in ("已作废", "已完成")
    )
    needs_supplementary = (
        not credential["ok"]
        and current is not None
        and str(current.get("status", "")) != CHECK_STATUS_PASSED
        and str(voucher.get("status", "")) in VOUCHER_ACTIVE + ("已作废",)
    )

    return {
        "credential": credential,
        "current_check": current,
        "node": node,
        "item": item,
        "blockers": blockers,
        "can_complete": can_complete,
        "needs_supplementary_check": needs_supplementary,
        "check_type": check_type,
    }


def get_acceptance_voucher(voucher_no: str) -> dict[str, Any]:
    """重新打开办理凭据：返回能否完成、是否需补检查、同名节点变化与历次电检结论。"""
    voucher = _find_voucher(voucher_no)
    if voucher is None:
        return {"ok": False, "reason": f"办理编号 {voucher_no} 不存在"}

    booth_no = str(voucher.get("展位编号", ""))
    node_name = str(voucher.get("节点名称", ""))
    source_check = find_check(str(voucher.get("检查编号", "")))
    check_type = str(source_check.get("检查类型", "电检")) if source_check else "电检"
    history = check_history(booth_no, node_name, check_type)

    completion = _voucher_completion(voucher)
    node = completion["node"]

    snapshot = voucher.get("同类节点快照", [])
    peers_changed, peers = (
        _peers_changed(node, snapshot) if node is not None else (False, [])
    )

    related_changes = [
        co
        for co in store.rows("change_order")
        if booth_no in str(co.get("影响展位", ""))
    ]

    conclusions = [
        {
            "check_no": c.get("检查编号"),
            "round": c.get("轮次"),
            "status": c.get("status"),
            "conclusion": (
                (c.get("原结论") or c.get("结论"))
                if str(c.get("status", "")) == CHECK_STATUS_SUPERSEDED
                else c.get("结论")
            ),
            "superseded": str(c.get("status", "")) == CHECK_STATUS_SUPERSEDED,
            "reason": c.get("作废原因") or c.get("重开原因") or "",
            "is_current": str(c.get("status", "")) != CHECK_STATUS_SUPERSEDED,
        }
        for c in history
    ]
    new_check_no = (
        completion["current_check"].get("检查编号")
        if completion["current_check"]
        else None
    )

    return {
        "ok": True,
        "voucher_no": voucher_no,
        "voucher": voucher,
        "checklist_item": completion["item"],
        "node": completion["node"],
        "booth_no": booth_no,
        "node_name": node_name,
        "status": voucher.get("status"),
        "signoff_status": voucher.get("签收状态"),
        "can_complete": completion["can_complete"],
        "needs_supplementary_check": completion["needs_supplementary_check"],
        "completion_blockers": completion["blockers"],
        "credential_valid": completion["credential"]["ok"],
        "credential": completion["credential"],
        "old_check_no": voucher.get("检查编号"),
        "current_check_no": new_check_no,
        "current_check": completion["current_check"],
        "check_conclusions": conclusions,
        "check_conclusion_count": len(conclusions),
        "two_conclusions": len(conclusions) >= 2,
        "same_name_nodes": peers,
        "same_name_nodes_changed": peers_changed,
        "related_change_orders": related_changes,
        "history_lookup": {
            "old_check_no": voucher.get("检查编号"),
            "lookup_available": True,
            "superseded_by": voucher.get("替代检查编号"),
        },
    }


def submit_voucher_signoff(
    voucher_no: str, *, check_no: str | None = None, remark: str | None = None
) -> dict[str, Any]:
    """提交签收但尚未收到结果；提交时校验一次办理凭据。"""
    voucher = _find_voucher(voucher_no)
    if voucher is None:
        return {"ok": False, "reason": f"办理编号 {voucher_no} 不存在"}
    if str(voucher.get("status", "")) in ("已作废", "已完成"):
        return {
            "ok": False,
            "reason": (
                f"办理凭据 {voucher_no} 当前状态为 {voucher.get('status')}，不能提交签收"
            ),
            "voucher_no": voucher_no,
        }

    credential_no = check_no or str(voucher.get("检查编号", ""))
    if check_no and str(check_no) != str(voucher.get("检查编号", "")):
        return {
            "ok": False,
            "reason": (
                f"提交的检查编号 {check_no} 与办理凭据关联的 "
                f"{voucher.get('检查编号')} 不一致"
            ),
        }
    credential = validate_credential(
        credential_no,
        booth_no=str(voucher.get("展位编号", "")),
        node_name=str(voucher.get("节点名称", "")),
    )
    if not credential["ok"]:
        return {
            "ok": False,
            "reason": credential["reason"],
            "credential": credential,
            "voucher_no": voucher_no,
        }

    before_state = copy.deepcopy(voucher)
    voucher["status"] = "已提交"
    voucher["签收状态"] = "已提交"
    voucher["结果"] = "待结果"
    voucher["pending"] = True
    voucher["提交时间"] = _now()
    if remark:
        voucher["备注说明"] = f"{voucher.get('备注说明', '')}；{remark}".strip("；")
    store.event_log.record(
        module="acceptance_voucher",
        entry_id=int(voucher.get("id", 0)),
        action="提交签收",
        before=before_state,
        after=copy.deepcopy(voucher),
        extra={
            "booth_no": voucher.get("展位编号", ""),
            "voucher_no": voucher_no,
            "check_no": credential_no,
            "result": "待结果",
        },
    )
    store.rebuild_indices()
    return {
        "ok": True,
        "reason": "签收已提交，等待结果",
        "voucher_no": voucher_no,
        "voucher": voucher,
        "result_pending": True,
        "credential": credential,
    }


def check_safety_item(booth_no: str) -> dict[str, Any]:
    """复用安全巡检门禁结论（不反向导入 exhibition，保持模块独立）。"""
    inspections = store.booth_safety(booth_no)
    failed = [
        {
            "id": i.get("id"),
            "point": i.get("检查点位", ""),
            "level": i.get("隐患等级", ""),
            "status": i.get("status", ""),
        }
        for i in inspections
        if str(i.get("status", "")) != "已确认"
    ]
    return {
        "ok": len(failed) == 0,
        "reason": "" if not failed else f"展位 {booth_no} 有 {len(failed)} 条巡检未通过",
        "total_inspections": len(inspections),
        "failed_inspections": failed,
    }


def signoff_with_credential(
    checklist_id: int,
    *,
    check_no: str | None = None,
    voucher_no: str | None = None,
    node_id: int | None = None,
) -> dict[str, Any]:
    """用办理凭据/检查号签收验收项；无效的旧电检凭据会被拦住。"""
    item = store.find("checklist", checklist_id)
    if item is None:
        return {"ok": False, "reason": f"验收项 {checklist_id} 不存在"}
    booth_no = str(item.get("负责班组", ""))

    voucher: dict[str, Any] | None = None
    credential_no = check_no
    if voucher_no:
        voucher = _find_voucher(voucher_no)
        if voucher is None:
            return {"ok": False, "reason": f"办理编号 {voucher_no} 不存在"}
        if voucher.get("验收项ID") is None or int(voucher.get("验收项ID")) != int(
            checklist_id
        ):
            return {
                "ok": False,
                "reason": (
                    f"办理凭据 {voucher_no} 属于验收项 {voucher.get('验收项ID')}，"
                    f"与目标验收项 {checklist_id} 不一致"
                ),
            }
        if str(voucher.get("status", "")) == "已作废":
            return {
                "ok": False,
                "reason": (
                    f"办理凭据 {voucher_no} 已失效："
                    f"{voucher.get('作废原因') or '关联检查已重开'}"
                ),
                "voucher_no": voucher_no,
                "voucher": voucher,
                "invalid_credential": True,
            }
        credential_no = credential_no or str(voucher.get("检查编号", ""))
        if str(credential_no) != str(voucher.get("检查编号", "")):
            return {
                "ok": False,
                "reason": (
                    f"检查编号 {credential_no} 与办理凭据 {voucher_no} 关联的 "
                    f"{voucher.get('检查编号')} 不一致"
                ),
            }

    if credential_no:
        credential = validate_credential(
            str(credential_no),
            booth_no=booth_no,
            node_name=str(voucher.get("节点名称")) if voucher else None,
        )
        if not credential["ok"]:
            return {
                "ok": False,
                "reason": credential["reason"],
                "check_no": str(credential_no),
                "credential": credential,
                "invalid_credential": True,
            }
    else:
        credential = None

    safety = check_safety_item(booth_no)
    if not safety["ok"]:
        return {
            "ok": False,
            "reason": (
                f"展位 {booth_no} 安全巡检未通过，"
                f"验收项「{item.get('验收条目', '')}」不可签收"
            ),
            "safety_check": safety,
        }

    # 进度节点前置与电检阻塞仍需满足。
    node = (
        store.find("construction", node_id)
        if node_id is not None
        else (
            store.find("construction", int(voucher.get("进度节点ID")))
            if voucher and voucher.get("进度节点ID") is not None
            else None
        )
    )
    if node is not None:
        scoped = [
            n
            for n in store.rows("construction")
            if _booth_of_node(n) == _booth_of_node(node)
        ]
        blockers = _predecessor_blockers(node, scoped) + _check_blockers(node, booth_no)
        if blockers:
            return {
                "ok": False,
                "reason": blockers[0]["reason"],
                "blockers": blockers,
            }

    before_item = copy.deepcopy(item)
    item["status"] = "已确认"
    item["pending"] = False
    item["abnormal"] = False
    store.event_log.record(
        module="checklist",
        entry_id=checklist_id,
        action="签收验收",
        before=before_item,
        after=copy.deepcopy(item),
        extra={
            "booth_no": booth_no,
            "check_no": credential_no,
            "voucher_no": voucher_no,
        },
    )
    if voucher is not None:
        before_voucher = copy.deepcopy(voucher)
        voucher["status"] = "已完成"
        voucher["签收状态"] = "已完成"
        voucher["结果"] = "已签收"
        voucher["pending"] = False
        voucher["完成时间"] = _now()
        store.event_log.record(
            module="acceptance_voucher",
            entry_id=int(voucher.get("id", 0)),
            action="签收完成",
            before=before_voucher,
            after=copy.deepcopy(voucher),
            extra={
                "booth_no": booth_no,
                "voucher_no": voucher_no,
                "check_no": credential_no,
                "checklist_id": checklist_id,
            },
        )
    store.rebuild_indices()
    return {
        "ok": True,
        "reason": "签收完成",
        "item": item,
        "voucher": voucher,
        "voucher_no": voucher_no,
        "check_no": credential_no,
        "credential": credential,
        "safety_check": safety,
    }


def record_check_result(
    check_no: str, *, passed: bool, conclusion: str = "", operator: str = ""
) -> dict[str, Any]:
    """录入某一轮前置检查结论（通过/未通过），旧轮次不能录入。"""
    check = find_check(check_no)
    if check is None:
        return {"ok": False, "reason": f"检查编号 {check_no} 不存在"}
    if str(check.get("status", "")) == CHECK_STATUS_SUPERSEDED:
        return {
            "ok": False,
            "reason": (
                f"检查编号 {check_no} 已重开作废，不能在该旧轮次上录入结论；"
                f"请使用当前检查 {check.get('替代检查编号', '')}"
            ),
            "check_no": check_no,
            "current_check_no": check.get("替代检查编号"),
        }

    booth_no = str(check.get("展位编号", ""))
    node_name = str(check.get("节点名称", ""))
    check_type = str(check.get("检查类型", ""))
    latest = latest_round(booth_no, node_name, check_type)
    if latest is not None and int(check.get("轮次", 1)) < int(latest.get("轮次", 1)):
        return {
            "ok": False,
            "reason": (
                f"检查编号 {check_no} 是旧轮次，当前应为 {latest.get('检查编号')}，"
                "不能从旧轮次结论继续签发凭据"
            ),
            "check_no": check_no,
            "current_check_no": latest.get("检查编号"),
        }

    before_state = copy.deepcopy(check)
    check["status"] = CHECK_STATUS_PASSED if passed else "未通过"
    check["结论"] = conclusion or ("通过" if passed else "未通过")
    check["pending"] = not passed
    check["abnormal"] = not passed
    if operator:
        check["负责人"] = operator
    store.event_log.record(
        module="prerequisite_check",
        entry_id=int(check.get("id", 0)),
        action="录入检查结论",
        before=before_state,
        after=copy.deepcopy(check),
        extra={
            "booth_no": booth_no,
            "check_no": check_no,
            "round": check.get("轮次"),
            "conclusion": check["结论"],
            "passed": passed,
        },
    )
    store.rebuild_indices()

    vouchers = [
        v
        for v in store.rows("acceptance_voucher")
        if str(v.get("检查编号", "")) == check_no
        and str(v.get("status", "")) in VOUCHER_ACTIVE
    ]
    return {
        "ok": True,
        "reason": (
            f"检查 {check_no} 结论已录入：{check['结论']}"
            + ("，可签发办理凭据" if passed else "，不能签发办理凭据")
        ),
        "check": check,
        "check_no": check_no,
        "passed": passed,
        "can_issue_voucher": passed,
        "active_vouchers": [v.get("办理编号") for v in vouchers],
    }


def checklist_credential_summary(checklist_id: int) -> dict[str, Any]:
    """验收清单条目上的办理凭据摘要，供列表/详情直接展示。"""
    vouchers = _vouchers_for_checklist(checklist_id)
    active = [v for v in vouchers if str(v.get("status", "")) in VOUCHER_ACTIVE]
    return {
        "voucher_count": len(vouchers),
        "active_voucher_no": active[0].get("办理编号") if active else "",
        "voucher_no": vouchers[-1].get("办理编号") if vouchers else "",
        "voucher_status": vouchers[-1].get("status") if vouchers else "",
        "check_no": vouchers[-1].get("检查编号") if vouchers else "",
    }


def list_prerequisite_checks(
    booth_no: str | None = None,
    *,
    node_name: str | None = None,
    check_type: str | None = None,
    include_superseded: bool = False,
) -> dict[str, Any]:
    rows = checks_for(
        booth_no,
        node_name=node_name,
        check_type=check_type,
        include_superseded=include_superseded,
    )
    return {"items": rows, "total": len(rows)}


# 兼容命名
lookup_check = check_detail
