"""验收办理领域服务：签发、提交、完成与作废办理凭据，联动验收清单签收。"""
from __future__ import annotations

from typing import Any

from app.services import acceptance
from app.services.base import BaseModuleService
from app.store import store


class AcceptanceVoucherService(BaseModuleService):
    MODULE = "acceptance_voucher"
    ENTITY = "办理凭据"
    OPERATION_TERM = "提交签收"
    LIST_FIELDS = [
        "办理编号", "验收条目", "展位编号", "节点名称", "检查编号", "检查轮次",
        "签收状态", "结果", "签发时间", "作废原因", "登记编号", "负责人", "备注说明",
    ]
    REQUIRED_FIELDS = ["办理编号", "验收条目", "展位编号", "节点名称", "检查编号"]
    STATUS_ORDER = ["待提交", "已提交", "已完成", "已作废"]
    ACTION_RULES = {"提交签收": "已提交", "完成签收": "已完成", "作废办理": "已作废"}
    NEGATIVE_ACTIONS = ["作废办理"]
    RELATED_MODULES = ["checklist", "prerequisite_check", "construction"]

    def validate_entry(self, values: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        check_no = str(values.get("检查编号", "")).strip()
        booth_no = str(values.get("展位编号", "")).strip()
        node_name = str(values.get("节点名称", "")).strip()
        if check_no:
            credential = acceptance.validate_credential(
                check_no, booth_no=booth_no or None, node_name=node_name or None
            )
            if not credential["ok"]:
                errors.append(credential["reason"])
        return errors

    def validate_action(self, entry_id: int, action: str) -> tuple[bool, str]:
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return False, "办理凭据不存在"
        if action in ("提交签收", "完成签收") and str(entry.get("status", "")) == "已作废":
            return False, f"办理凭据 {entry.get('办理编号')} 已作废，不能{action}"
        return True, ""

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None, f"办理凭据 {entry_id} 不存在或已归档"
        voucher_no = str(entry.get("办理编号", ""))

        if action in ("提交签收", "完成签收"):
            checklist_id = entry.get("验收项ID")
            submit = acceptance.submit_voucher_signoff(voucher_no)
            if not submit["ok"]:
                return None, submit["reason"]
            if action == "完成签收":
                result = acceptance.signoff_with_credential(
                    int(checklist_id), voucher_no=voucher_no
                )
                if not result["ok"]:
                    return None, result["reason"]
                return result["voucher"], result["reason"]
            return submit["voucher"], submit["reason"]

        if action == "作废办理":
            entry["status"] = "已作废"
            entry["签收状态"] = "已作废"
            entry["pending"] = False
            entry["abnormal"] = True
            entry["作废原因"] = "手工作废"
            return entry, f"办理凭据 {voucher_no} 已作废"

        return super().run_action(entry_id, action)

    def domain_snapshot(self) -> dict[str, Any]:
        base = super().domain_snapshot()
        rows = store.rows(self.MODULE)
        base["invalidated_count"] = sum(1 for r in rows if r.get("status") == "已作废")
        base["pending_count"] = sum(1 for r in rows if r.get("status") in acceptance.VOUCHER_ACTIVE)
        return base
