# 会展布展协作平台

策展人、设计师和施工团队共同编排展位布局、展品运输与搭建进度，按同一版执行方案完成布展交付。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/WorkbenchView.vue|tsx  全部模块共享工作台
│   ├── src/data/modules.ts              18个业务模块配置
│   ├── src/api/              统一请求封装
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/resource.py  通用查询/导出/登记/动作接口
│   ├── app/services/<key>.py    每个模块独立领域逻辑
│   ├── app/services/base.py     共享服务骨架
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm ci
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 场馆规划 | `venue` | 场馆 | 场馆名称、可用面积、层高限制 |
| 展位编排 | `booth` | 展位 | 展位编号、面积尺寸、开口方向 |
| 参展商管理 | `exhibitor` | 参展商 | 企业名称、展品类别、联系人 |
| 方案设计 | `design` | 设计方案 | 设计风格、结构材料、搭建高度 |
| 搭建物料 | `material` | 物料 | 物料名称、规格型号、配额数量 |
| 展品运输 | `transport` | 运输单 | 展品名称、运输方式、预计到达 |
| 搭建进度 | `construction` | 进度节点 | 节点名称、计划日期、完成日期 |
| 用电配置 | `electrical` | 用电回路 | 回路编号、额定功率、所属展位 |
| 安全巡检 | `safety` | 巡检记录 | 检查点位、隐患等级、整改措施 |
| 灯光编排 | `lighting` | 灯光方案 | 灯位坐标、色温设定、光束角度 |
| 影音布置 | `audio_visual` | 影音设备 | 设备型号、安装位置、信号线路 |
| 家具配置 | `furniture` | 家具方案 | 家具类型、摆放位置、数量需求 |
| 导视系统 | `signage` | 导视牌 | 指示内容、安装点位、尺寸规格 |
| 验收清单 | `checklist` | 验收项 | 验收条目、验收标准、负责班组 |
| 验收办理 | `acceptance_voucher` | 办理凭据 | 办理编号、检查编号、签收状态 |
| 前置检查 | `prerequisite_check` | 检查记录 | 检查编号、检查类型、轮次、结论 |
| 变更指令 | `change_order` | 变更单 | 变更内容、影响展位、施工班组 |
| 布展排期 | `schedule` | 排期计划 | 活动名称、布展起始、撤展截止 |
| 交场确认 | `handover` | 交场单 | 交出班组、接收人员、遗留事项 |
| 突发事件 | `incident` | 事件记录 | 事件类型、发生位置、处置班组 |

## 约定

- 全部模块共享`frontend/src/views/WorkbenchView.vue|tsx`和一套资源路由。
- 每个模块仍保留独立`backend/app/services/<模块>.py`；纯前端保留
  `frontend/src/domain/<模块>.ts`，用于承载真实业务差异并维持36题位容量。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。
- 同名进度节点按展位分别判断（DAG 校验、阻塞待办都只在同一展位内建图/比对）。

## 施工待办与验收办理

搭建进度的待办入口在 `/blocking-todos` 页面，也可直接调接口：

- `GET /api/exhibition/construction/todos?blocked_by=电检&booth_no=BOOT-A01`
  按阻塞源（前置节点 / 电检 / 安全巡检）筛选施工待办。
- `GET /api/exhibition/checks/{检查编号}` 值班员按检查号回看该轮筛查结论，
  已重开作废的旧轮次仍返回原结论。
- `POST /api/exhibition/checklist/{验收项id}/voucher` 从进度节点 + 当前有效的
  已通过电检签发办理凭据。
- `POST /api/exhibition/vouchers/{办理编号}/submit` 提交签收（结果待回）。
- `GET /api/exhibition/vouchers/{办理编号}` 重新打开原办理：能否完成、是否需补检查、
  同一次签收的多份电检结论、以及其它展位同名节点是否变化。
- `POST /api/exhibition/checklist/{验收项id}/credential-signoff` 用凭据/检查号签收；
  已被重开的旧检查编号会被拦住。

变更单签发时会重开受影响展位的电检前置检查（旧轮次留结论可查），
并从旧结论签发的办理凭据一并作废；同一轮旧检查不能重复重开。

领域：应用开发
子方向：web前端/全栈开发
