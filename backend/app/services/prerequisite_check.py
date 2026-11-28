"""前置检查领域服务：按检查号回看轮次结论，重开检查与录入结论走 acceptance 引擎。"""
from __future__ import annotations

from typing import Any

from app.services import acceptance
from app.services.base import BaseModuleService
from app.store import store


class PrerequisiteCheckService(BaseModuleService):
    MODULE = "prerequisite_check"
    ENTITY = "检查记录"
    OPERATION_TERM = "录入检查结论"
    LIST_FIELDS = [
        "检查编号", "检查类型", "展位编号", "节点名称", "轮次", "结论",
        "原检查编号", "复查日期", "登记编号", "负责人", "生效版本", "备注说明",
    ]
    REQUIRED_FIELDS = ["检查编号", "检查类型", "展位编号", "节点名称"]
    STATUS_ORDER = ["待检", "已通过", "未通过", "已作废"]
    ACTION_RULES = {"录入检查结论": "已通过", "重开检查": "已作废", "查看历史": "已作废"}
    NEGATIVE_ACTIONS = ["重开检查"]
    RELATED_MODULES = ["construction", "acceptance_voucher", "checklist"]

    def validate_entry(self, values: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        booth_no = str(values.get("展位编号", "")).strip()
        if booth_no and store.find_booth(booth_no) is None:
            errors.append(f"展位 {booth_no} 不存在，请先登记展位")
        node_name = str(values.get("节点名称", "")).strip()
        if booth_no and node_name:
            matched = [
                n for n in store.rows("construction")
                if acceptance._booth_of_node(n) == booth_no
                and str(n.get("节点名称", "")) == node_name
            ]
            if not matched:
                errors.append(f"展位 {booth_no} 下没有名为「{node_name}」的进度节点")
        check_no = str(values.get("检查编号", "")).strip()
        if check_no and acceptance.find_check(check_no) is not None:
            errors.append(f"检查编号 {check_no} 已存在")
        return errors

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        entry, missing = super().create_entry(values)
        if entry is None:
            return entry, missing
        # 未显式给轮次时，按同展位同节点同类型当前最大轮次 +1 自动编号。
        if not entry.get("轮次"):
            booth_no = str(entry.get("展位编号", ""))
            node_name = str(entry.get("节点名称", ""))
            check_type = str(entry.get("检查类型", ""))
            latest = acceptance.latest_round(booth_no, node_name, check_type)
            entry["轮次"] = int(latest.get("轮次") or 0) + 1 if latest else 1
            entry["结论"] = entry.get("结论") or "待检"
        return entry, missing

    def validate_action(self, entry_id: int, action: str) -> tuple[bool, str]:
        if action in ("录入检查结论", "重开检查"):
            entry = store.find(self.MODULE, entry_id)
            if entry is None:
                return False, "检查记录不存在"
        return True, ""

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None, f"检查记录 {entry_id} 不存在或已归档"
        check_no = str(entry.get("检查编号", ""))

        if action == "录入检查结论":
            result = acceptance.record_check_result(check_no, passed=True)
            if not result["ok"]:
                return None, result["reason"]
            return result["check"], result["reason"]

        if action == "重开检查":
            result = acceptance.reopen_prerequisite_check(check_no, reason="手工重开")
            if not result["ok"]:
                return None, result["reason"]
            return result["new_check"], result["reason"]

        if action == "查看历史":
            return entry, f"检查 {check_no} 历史可通过 GET /api/exhibition/checks/{check_no} 查看"

        return super().run_action(entry_id, action)

    def domain_snapshot(self) -> dict[str, Any]:
        base = super().domain_snapshot()
        rows = store.rows(self.MODULE)
        base["superseded_count"] = sum(
            1 for r in rows if r.get("status") == acceptance.CHECK_STATUS_SUPERSEDED
        )
        return base
