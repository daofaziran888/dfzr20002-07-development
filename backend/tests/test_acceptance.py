"""施工待办、前置检查与验收办理凭据的确定性业务测试。

场景覆盖：
1. 施工待办按阻塞源（电检）筛选出被阻塞的 A01 节点；
2. 两个展位的同名节点分别判断；
3. 电检通过后签发办理凭据并提交签收（结果未回）；
4. 变更单重开电检后，同一次签收遇到两份电检结论；
5. 重新打开原办理：能否完成、是否需补检查、A02 同名节点是否变化；
6. 用旧检查编号发起新签收被拦住；
7. 值班员仍能按旧检查号回看先前筛查结论。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import acceptance, exhibition
from app.store import store


class AcceptanceScenarioBase(unittest.TestCase):
    """每个用例都在独立的数据快照上跑，避免修改种子影响其它测试。"""

    def setUp(self):
        self._backup = {
            name: [dict(row) for row in rows] for name, rows in store._tables.items()
        }
        self._id_backup = dict(store._id_counters)
        self._event_backup = list(store.event_log.entries)

    def tearDown(self):
        store._tables = {name: [dict(row) for row in rows] for name, rows in self._backup.items()}
        store._id_counters = dict(self._id_backup)
        store.event_log.entries = list(self._event_backup)
        store.rebuild_indices()


class TestConstructionTodoBlocking(AcceptanceScenarioBase):
    def test_blocked_by_electrical_filters_a01_nodes(self):
        """按电检筛选，应能筛出 A01 被电检阻塞的「饰面安装」节点。"""
        result = acceptance.construction_todos(blocked_by="电检", booth_no="BOOT-A01")
        names = [item["节点名称"] for item in result["items"]]
        self.assertIn("饰面安装", names, "A01 饰面安装应被电检阻塞")
        item = next(i for i in result["items"] if i["节点名称"] == "饰面安装")
        self.assertEqual(item["blocking_sources"], ["电检"])
        self.assertEqual(item["booth_no"], "BOOT-A01")
        self.assertEqual(item["related_checks"][0]["检查编号"], "ELEC-CHK-0002")

    def test_blocked_by_predecessor_excludes_electrical_only_nodes(self):
        """按前置节点筛选只保留确实有前置未完成的节点，不混入仅电检阻塞的节点。"""
        result = acceptance.construction_todos(blocked_by="前置节点", booth_no="BOOT-A01")
        names = [item["节点名称"] for item in result["items"]]
        # 「灯光影音联调」的前置「饰面安装」未完成，应命中前置节点筛选。
        self.assertIn("灯光影音联调", names)
        item = next(i for i in result["items"] if i["节点名称"] == "灯光影音联调")
        self.assertEqual(item["blocking_sources"], ["前置节点"])
        # 「饰面安装」只被电检阻塞（前置已确认），不应进入前置节点筛选结果。
        self.assertNotIn("饰面安装", names)

    def test_blocked_by_predecessor_counts_dependency_only(self):
        """被电检阻塞的节点若同时有前置阻塞，两源都应列出。"""
        result = acceptance.construction_todos(blocked_by="电检", booth_no="BOOT-A01")
        item = next(i for i in result["items"] if i["节点名称"] == "饰面安装")
        self.assertEqual(
            [b["source"] for b in item["blockers"]], ["电检"],
            "饰面安装的前置「强弱电布线」已确认，只剩电检阻塞",
        )

    def test_source_counts_exposed(self):
        """阻塞源清单与数量可直接作为筛选项展示。"""
        sources = acceptance.todo_sources(booth_no="BOOT-A01")["sources"]
        names = {s["source"] for s in sources}
        self.assertIn("电检", names)
        self.assertIn("前置节点", names)

    def test_todos_are_booth_scoped(self):
        """A01 与 A02 的待办应分别归属，不混用同名的前置判断。"""
        all_items = acceptance.construction_todos()["items"]
        a01 = [i for i in all_items if i["booth_no"] == "BOOT-A01"]
        a02 = [i for i in all_items if i["booth_no"] == "BOOT-A02"]
        self.assertTrue(a01 and a02)
        # A02 的「基础结构搭建」没有前置，被电检 + 安全巡检阻塞；A01 的同名节点已确认且电检通过。
        a02_base = next(i for i in a02 if i["节点名称"] == "基础结构搭建")
        self.assertIn("电检", a02_base["blocking_sources"])
        self.assertEqual(a02_base["booth_no"], "BOOT-A02")
        self.assertNotIn(
            "基础结构搭建",
            [i["节点名称"] for i in a01],
            "A01 的基础结构搭建已确认且电检通过，不应出现在待办",
        )
        # 同名节点状态不同：A02 基础结构搭建待确认，A01 同名节点已确认。
        a02_node = next(
            n for n in store.rows("construction")
            if n["id"] == 6
        )
        a01_node = next(
            n for n in store.rows("construction")
            if n["id"] == 1
        )
        self.assertEqual(a02_node["status"], "待确认")
        self.assertEqual(a01_node["status"], "已确认")


class TestSameNameNodesSeparate(AcceptanceScenarioBase):
    def test_same_name_nodes_judged_separately_in_dag(self):
        """A01 的「基础结构搭建」已确认，A02 同名节点待确认；推进 A02 时应按 A02 判断。"""
        a02_base = next(
            n for n in store.rows("construction")
            if n["id"] == 6
        )
        a02_wiring = next(n for n in store.rows("construction") if n["id"] == 7)
        # A02 的「强弱电布线」前置是 A02 的「基础结构搭建」，尚未完成，应被拦截。
        result = exhibition.validate_dag_advance(7)
        self.assertFalse(result["ok"], "A02 前置未完成应被拦截")
        self.assertEqual(result["booth_no"], "BOOT-A02")

        # A01 的「强弱电布线」前置已确认，可以推进。
        result_a01 = exhibition.validate_dag_advance(2)
        self.assertTrue(result_a01["ok"])
        self.assertEqual(result_a01["booth_no"], "BOOT-A01")

    def test_a01_confirmed_does_not_unlock_a02_same_name(self):
        """A01 同名节点已确认，不应让 A02 的同名前置自动变成已完成。"""
        scoped = [
            n for n in store.rows("construction")
            if exhibition.node_booth(n) == "BOOT-A02"
        ]
        a02_base = next(n for n in scoped if n["节点名称"] == "基础结构搭建")
        self.assertEqual(a02_base["status"], "待确认")


class TestVoucherSignoffScenario(AcceptanceScenarioBase):
    def _complete_electrical(self, check_no: str, conclusion: str = "通过") -> dict:
        return acceptance.record_check_result(check_no, passed=True, conclusion=conclusion)

    def _issue_and_submit(self) -> tuple[dict, dict]:
        issue = acceptance.issue_acceptance_voucher(2, node_id=3)
        self.assertTrue(issue["ok"], f"电检通过后应能签发凭据: {issue.get('reason')}")
        submit = acceptance.submit_voucher_signoff(issue["voucher_no"])
        self.assertTrue(submit["ok"], f"提交签收应成功: {submit.get('reason')}")
        return issue, submit

    def test_full_flow_reopen_reveals_two_conclusions(self):
        """电检通过→签发→提交→变更重开电检→重新打开原办理。"""
        # 1. 电检通过
        self._complete_electrical("ELEC-CHK-0002", "第1轮电检通过")
        # 2. 签发并提交（尚未收到结果）
        issue, submit = self._issue_and_submit()
        voucher_no = issue["voucher_no"]
        self.assertEqual(submit["voucher"]["结果"], "待结果")
        self.assertEqual(submit["voucher"]["status"], "已提交")

        # 3. 变更单重开电检（变更单登记影响 A01）
        change_id = store.next_id("change_order")
        store.rows("change_order").append({
            "id": change_id,
            "status": "待确认",
            "pending": True,
            "abnormal": False,
            "变更内容": "A01 饰面安装调整电检方案",
            "影响展位": "BOOT-A01",
            "施工班组": "电气施工组",
            "签收时限": "2026-09-20",
            "登记编号": "CHAN-0002",
            "负责人": "张策展",
            "生效版本": "v1.0",
            "备注说明": "重开 A01 电检",
        })
        propagation = exhibition.propagate_change_order(change_id)
        self.assertTrue(propagation["ok"], propagation.get("reason"))
        self.assertGreaterEqual(len(propagation["reopened_checks"]), 1)
        self.assertGreaterEqual(len(propagation["invalidated_vouchers"]), 1)

        # 4. 重新打开刚才提交的原办理
        reopened = acceptance.get_acceptance_voucher(voucher_no)
        self.assertTrue(reopened["ok"])
        self.assertFalse(reopened["can_complete"], "凭据已作废，不能直接完成签收")
        self.assertTrue(reopened["needs_supplementary_check"], "应提示需要补检查")
        self.assertTrue(reopened["two_conclusions"], "同一次签收应看到两份电检结论")
        self.assertEqual(
            reopened["check_conclusion_count"], 2,
            "第1轮旧结论与第2轮新检查应同时可见",
        )
        expected_current = acceptance.current_check("BOOT-A01", "饰面安装", "电检")["检查编号"]
        self.assertEqual(reopened["current_check_no"], expected_current)
        # A02 同名节点未受 A01 变更影响，应显示“无变化”，证明两展位分别判断。
        self.assertFalse(
            reopened["same_name_nodes_changed"],
            "变更只影响 A01，A02 同名节点不应被连带动到",
        )
        peer = next(p for p in reopened["same_name_nodes"] if p["booth_no"] == "BOOT-A02")
        self.assertEqual(peer["node_id"], 8)
        self.assertFalse(peer["changed"])
        self.assertEqual(peer["reason"], "无变化")

    def test_change_touching_both_booths_reports_a02_peer_changed(self):
        """若变更同时影响 A02，重新打开办理时应看到 A02 同名节点发生变化。"""
        acceptance.record_check_result("ELEC-CHK-0002", passed=True, conclusion="第1轮通过")
        issue, _ = self._issue_and_submit()
        voucher_no = issue["voucher_no"]

        change_id = store.next_id("change_order")
        store.rows("change_order").append({
            "id": change_id,
            "status": "待确认",
            "pending": True,
            "abnormal": False,
            "变更内容": "A01/A02 电检方案调整",
            "影响展位": "BOOT-A01,BOOT-A02",
            "施工班组": "电气施工组",
            "签收时限": "2026-09-20",
            "登记编号": "CHAN-0003",
            "负责人": "张策展",
            "生效版本": "v1.0",
            "备注说明": "两个展位电检都重开",
        })
        exhibition.propagate_change_order(change_id)

        reopened = acceptance.get_acceptance_voucher(voucher_no)
        self.assertTrue(reopened["same_name_nodes_changed"])
        peer = next(p for p in reopened["same_name_nodes"] if p["booth_no"] == "BOOT-A02")
        self.assertTrue(peer["changed"])
        self.assertEqual(peer["check_round"], 2)
        expected_a02 = acceptance.current_check("BOOT-A02", "饰面安装", "电检")["检查编号"]
        self.assertEqual(peer["check_no"], expected_a02)

    def test_old_check_no_blocked_for_new_signoff(self):
        """用关联的旧检查编号发起新签收，应被拦住。"""
        self._complete_electrical("ELEC-CHK-0002")
        old_check_no = store.rows("prerequisite_check")[1]["检查编号"]  # ELEC-CHK-0002
        acceptance.reopen_prerequisite_check(old_check_no, reason="测试重开")
        result = acceptance.signoff_with_credential(2, check_no=old_check_no, node_id=3)
        self.assertFalse(result["ok"], "旧检查编号不能通过新签收")
        self.assertTrue(result.get("invalid_credential"))
        self.assertIn("作废", result["reason"])

    def test_old_check_still_lookupable(self):
        """值班员仍能按旧检查号回看先前筛查结果。"""
        old_check_no = "ELEC-CHK-0002"
        record = acceptance.record_check_result(old_check_no, passed=True, conclusion="第1轮通过")
        self.assertTrue(record["ok"])
        acceptance.reopen_prerequisite_check(old_check_no, reason="变更重开")
        detail = acceptance.check_detail(old_check_no)
        self.assertTrue(detail["ok"], "旧检查号应仍可回看")
        self.assertFalse(detail["is_current"])
        self.assertEqual(detail["check"]["结论"], "第1轮通过")
        self.assertEqual(detail["check"]["原结论"], "第1轮通过")
        self.assertTrue(detail["lookup_available"])
        self.assertEqual(detail["superseded_by"], "ELEC-CHK-0005")
        self.assertEqual(detail["round_count"], 2)

    def test_reopen_twice_rejected(self):
        """同一轮旧检查不能重复重开。"""
        acceptance.reopen_prerequisite_check("ELEC-CHK-0002", reason="第一次")
        second = acceptance.reopen_prerequisite_check("ELEC-CHK-0002", reason="第二次")
        self.assertFalse(second["ok"])
        self.assertIn("已经作废", second["reason"])

    def test_new_signoff_with_current_check_passes(self):
        """重开后用当前新检查号（通过）可以完成新的签收。"""
        acceptance.reopen_prerequisite_check("ELEC-CHK-0002", reason="变更重开")
        new_no = acceptance.current_check("BOOT-A01", "饰面安装", "电检")["检查编号"]
        acceptance.record_check_result(new_no, passed=True, conclusion="第2轮通过")
        issue = acceptance.issue_acceptance_voucher(2, node_id=3, check_no=new_no)
        self.assertTrue(issue["ok"], issue.get("reason"))
        result = acceptance.signoff_with_credential(2, voucher_no=issue["voucher_no"])
        self.assertTrue(result["ok"], result.get("reason"))
        self.assertEqual(result["item"]["status"], "已确认")


class TestVoucherIssueRules(AcceptanceScenarioBase):
    def test_issue_requires_passed_current_check(self):
        """电检未通过时不能签发凭据。"""
        result = acceptance.issue_acceptance_voucher(2, node_id=3)
        self.assertFalse(result["ok"], "ELEC-CHK-0002 未通过，不应签发凭据")
        self.assertIn("没有可用的已通过前置检查", result["reason"])

    def test_issue_rejects_wrong_booth_check(self):
        """A02 的检查号不能给 A01 的验收项签发凭据。"""
        result = acceptance.issue_acceptance_voucher(2, node_id=3, check_no="ELEC-CHK-0003")
        self.assertFalse(result["ok"])
        self.assertIn("展位", result["reason"])

    def test_same_name_voucher_snapshot_tracks_peer(self):
        """凭据签发时记录 A02 同名节点快照，重开后能比对变化。"""
        acceptance.record_check_result("ELEC-CHK-0002", passed=True)
        issue = acceptance.issue_acceptance_voucher(2, node_id=3)
        self.assertTrue(issue["ok"])
        snapshot = issue["voucher"]["同类节点快照"]
        self.assertTrue(any(s["booth_no"] == "BOOT-A02" for s in snapshot))
        peer = next(s for s in snapshot if s["booth_no"] == "BOOT-A02")
        self.assertEqual(peer["node_id"], 8)


class TestCheckResultRules(AcceptanceScenarioBase):
    def test_cannot_record_result_on_superseded_round(self):
        """重开后的旧轮次不能再录入结论。"""
        acceptance.reopen_prerequisite_check("ELEC-CHK-0002", reason="重开")
        result = acceptance.record_check_result("ELEC-CHK-0002", passed=True)
        self.assertFalse(result["ok"])
        self.assertIn("已重开作废", result["reason"])

    def test_pass_marks_check_issueable(self):
        """录入通过后检查变为已通过，可签发凭据。"""
        result = acceptance.record_check_result("ELEC-CHK-0002", passed=True, conclusion="复核通过")
        self.assertTrue(result["ok"])
        self.assertEqual(result["check"]["status"], "已通过")
        self.assertTrue(result["can_issue_voucher"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
