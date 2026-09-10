# Kimi Claw 任务书：InfoRadar 站点维护与静态化改造

> 使用方式：完成「第 0 步前置准备」后，把「第一部分～第五部分」整体粘贴发给 Kimi Claw 作为任务指令，建议同时让它存入长期记忆。

---

## 第 0 步：前置准备（你本人完成，约 20 分钟，只需做一次）

Kimi Claw 在云端运行，**无法直接操作你的笔记本**。完成以下三件事，它才能接管工作：

- [ ] 1. 把 `D:\KimiData\kimi\workspace\info-radar` 整个项目（含 `data/radar.db`、模板、`config.yaml`、抓取脚本）推到 **GitHub 私有仓库**，仓库名建议 `info-radar`
- [ ] 2. 在 Cloudflare 控制台创建 **API Token**（权限：Pages 编辑 + DNS 编辑，仅限 inforadar.xin 这个 Zone），记录 Token 和 Account ID
- [ ] 3. 把仓库地址、CF Token、Account ID 通过私聊发给 Kimi Claw，并让它存入长期记忆（**不要发在群里**）

> ⚠️ 授权红线（吸取上次教训）：Token 权限按上面最小化勾选，不要给"全账户编辑"；Cloudflare 登录授权这类账号操作仍由你本人完成，不让 Claw 代点。

---

# 以下内容为发给 Kimi Claw 的任务书正文

## 一、项目档案（背景上下文）

- **项目**：InfoRadar（inforadar.xin），个人资讯聚合站
- **现状架构**：Windows 笔记本 → FastAPI（localhost:7100）→ SQLite（data/radar.db）→ cloudflared 隧道 → Cloudflare → 公网
- **已知问题**：
  1. 隧道依赖笔记本开机且登录桌面，现已宕机（CF 错误 1033），不可用
  2. 笔记本所在网络存在 DNS 劫持（53 端口透明代理），本地验证域名解析一律走 DoH：`--doh-url https://doh.pub/dns-query`
  3. 域名未备案，Cloudflare 免费版在国内移动网络下访问不稳（已知限制，暂不处理）
- **代码仓库**：GitHub 私有仓库 `info-radar`（地址见私聊）
- **既定决策**：网站向「静态生成 + Cloudflare Pages」架构迁移，放弃隧道方案
- **内容红线**：`fetch_full_content` 永远为 false，只输出摘要+原文链接，规避版权风险
- **交接文档**：仓库内 `docs/deployment-progress.md` 记录了完整部署历史，动手前必读

## 二、总体目标

把 InfoRadar 改造为**不依赖任何个人电脑**的架构：GitHub 仓库 → 定时生成静态页 → Cloudflare Pages 托管。改造完成后进入"自动维护 + 持续改进"模式。

## 三、阶段任务（按优先级顺序执行，每个阶段完成后汇报并等我确认再进下一阶段）

### 阶段 1：静态化改造（核心任务）

1. 阅读仓库代码与 `docs/deployment-progress.md`，梳理现有页面结构
2. 新建 `build.py`：读取 SQLite → 用现有 Jinja2 模板渲染全部静态页面到 `dist/`（首页/详情页/分类页/归档分页/about/404/feed.xml/sitemap.xml/robots.txt）
3. 动态路由改造为静态路径（如 `/article/{id}` → `/articles/{id}/`）
4. 接入 Pagefind 静态搜索，替代原后端搜索 API（原限流逻辑随之废弃）
5. 在仓库提 PR，列出改动清单，等我合并

### 阶段 2：部署与域名切换

1. 用我提供的 CF Token，通过 wrangler 将 `dist/` 部署到 Cloudflare Pages（Direct Upload 方式，避开每月构建次数上限）
2. 在 `xxx.pages.dev` 预览域名上完成全功能验证并提交验证报告
3. **暂停，等我确认**后：将 inforadar.xin 绑定到 Pages，删除指向旧隧道的 CNAME
4. 切换后 48 小时内密切观察，随时准备回滚（回滚预案：DNS 改回隧道，我本地重启隧道）

### 阶段 3：定时更新机制

1. 在仓库配置 GitHub Actions workflow：每 30 分钟运行「抓取 → 生成 → Pagefind → wrangler 部署」
2. SQLite 库随仓库版本化管理，每次运行增量抓取后提交回仓库
3. 验证 Actions 连续 3 次成功后，向我报告"笔记本正式解放"

### 阶段 4：监控与持续改进（长期）

1. 接入 UptimeRobot 或 CF Health Checks，宕机 5 分钟内通过聊天频道通知我
2. 移动端响应式检查与修复（DevTools 设备模拟逐项过）
3. 补 about 页（含版权声明）、OG 分享卡片、favicon
4. 接入 Cloudflare Web Analytics，每周一生成上周访问简报发给我

## 四、周期性任务（配置为你的定时任务）

| 频率 | 任务 |
| --- | --- |
| 每小时 | 探测 https://inforadar.xin ，非 200 立即告警并尝试诊断 |
| 每天 08:00 | 检查 GitHub Actions 昨夜运行记录，有失败则修复并汇报 |
| 每周一 09:00 | 生成周报：访问量、内容更新量、待办问题、改进建议 |

## 五、工作规则（每条都来自真实教训，严格遵守）

1. **改配置当场验证**：任何配置修改（尤其是 DNS），修改后立即用权威通道验证生效再离开，不允许"改完就走"。DNS 验证用注册局/DoH，不用公共递归缓存结果
2. **分阶段交付**：每完成一个阶段停下来汇报，等我确认再做下一阶段；不允许一口气全做完
3. **授权边界**：只做本任务书范围内的事；涉及账号登录、付费、删除资源的操作，先问我
4. **长超时预设**：凡需要人工参与的流程，预留 20–30 分钟等待，不设 5 分钟短超时
5. **内容版权红线**：只抓摘要，不抓全文；所有资讯页保留原文链接和来源署名
6. **成本控制**：GitHub Actions 单次运行控制在 3 分钟内；CF API 调用避免轮询风暴
7. **失败诚实**：任务卡住或失败，直接报告失败原因和你的判断，不允许给出"应该没问题"这类无验证的结论
8. **记忆沉淀**：每次任务结束，把关键事实（路径、ID、决策、坑）写入你的 MEMORY.md，并把过程文档更新到仓库 `docs/`

## 六、汇报格式

每次汇报包含四段：

```text
【做了什么】本次完成的具体动作（附 PR/部署链接）
【验证结果】如何验证的 + 证据（截图 / curl 输出 / 状态码）
【发现的问题】异常、风险、需要我决策的事
【下一步】计划做什么，等确认还是直接做
```
