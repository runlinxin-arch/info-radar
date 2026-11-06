# InfoRadar · 个人资讯雷达

**站点：[https://inforadar.xin](https://inforadar.xin)** · 每 4 小时自动更新 · 只提供摘要与原文链接

[![healthz](https://img.shields.io/website?url=https%3A%2F%2Finforadar.xin%2Fhealthz&label=healthz&up_message=fresh&down_message=stale)](https://inforadar.xin/healthz)
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

> 🚧 **此网站项目仍在开发阶段，并非最终完全体 :)**
> 具体缺口见下方「已知限制 / 路线图」。

把 **AI 资讯、世界与国内新闻、arXiv 学术论文**收敛到一个页面：每 4 小时自动抓取最新内容，
按板块展示摘要，点击可跳原文。附带英文点词解释、习语高亮、站内搜索与 RSS 订阅。

> 核心约束：**不转载全文**。所有条目只保留摘要 + 原文链接 + 来源署名，版权归原作者。

---

## 功能

| 功能 | 说明 |
|---|---|
| **6 个板块** | AI 资讯 / 世界新闻 / 国内新闻 / 学术 · AI/CS / 学术 · 交互设计 / 学术 · 心理学 |
| **14 个信息源**（配置中启用） | arXiv ×4、TechCrunch AI、极客公园、雷锋网、中新网 ×3、NPR、Sky News、ScienceDaily、PsyPost |
| **自动更新** | 启动时距上次成功更新 >2h 立即抓取；常驻期间每 30 分钟检查，>4h 自动刷新 |
| **摘要而非全文** | 规则式摘要（前 300–500 字 + 关键句），`fetch_full_content: false` |
| **双语阅读模式** | 英文条目可「精读」，点任意单词查音标/词性/释义/例句；内置 **283 条**习语俚语高亮 |
| **站内搜索** | 接 [Tavily](https://tavily.com/) API，双层限流（单 IP + 全站日限） |
| **RSS 订阅** | [`/feed.xml`](https://inforadar.xin/feed.xml)：最新 50 条，可直接加进 Feedly / Inoreader |
| **健康探针** | [`/healthz`](https://inforadar.xin/healthz)：`200` = 可用且内容新鲜，`503` = 停更超过 8 小时 |
| **搜索入口** | `/robots.txt`、`/sitemap.xml`、IndexNow 推送（Bing / Yandex / Seznam） |

---

## 架构

```
                     ┌──────────── Cloudflare（DNS + CDN + 边缘缓存）────────────┐
   访客 ──HTTPS──▶    │  inforadar.xin  →  Cloudflare Tunnel（出站长连接）          │
                     └──────────────────────────┬────────────────────────────────┘
                                                │ 无需开放任何入站端口
                     ┌──────────────────────────▼────────────────────────────────┐
                     │  应用主机（当前：Windows 笔记本 / 目标：云服务器）           │
                     │                                                            │
                     │   systemd / 启动项: cloudflared tunnel run inforadar        │
                     │   systemd / 启动项: pythonw run.py                          │
                     │        ├─ FastAPI  (127.0.0.1:7100)                        │
                     │        │    ├─ 静态页 + /api/*  + 限流中间件                │
                     │        │    └─ /healthz /robots.txt /sitemap.xml /feed.xml  │
                     │        ├─ 后台线程：每 30 分钟检查，>4h 触发抓取             │
                     │        └─ SQLite  data/radar.db（WAL）                      │
                     └────────────────────────────────────────────────────────────┘
```

数据流：`config.yaml` → **crawler**（RSS + 协议白名单）→ **processor**（摘要 + 标题去重）
→ **db**（入库 + 按板块裁剪）→ **api**（列表/详情/搜索/订阅）。

---

## 目录结构

```
info-radar/
├─ run.py                      # 启动服务（7100）+ 后台自动更新线程
├─ update.py                   # 独立更新入口（供定时任务 / 手动调用）
├─ probe_feeds.py              # 开发用：探测单个 RSS 源
├─ probe_feeds2.py             # 开发用：批量探测信息源
├─ config.yaml                 # ★ 配置与密钥（已 .gitignore，不入库）
├─ app/
│  ├─ api.py                   # 路由 / 限流 / healthz / robots·sitemap·feed
│  ├─ feeds.py                 # robots.txt、sitemap.xml、RSS 渲染（纯函数，可单测）
│  ├─ crawler.py               # RSS 抓取 + safe_link() 协议白名单
│  ├─ pipeline.py              # 更新流水线：抓取 → 去重 → 入库 → 裁剪
│  ├─ processor.py             # 规则式摘要 + 标题相似度去重
│  ├─ worddict.py              # 点词解释（词典聚合 + LLM 预留分支）
│  ├─ tavily_search.py         # Tavily 搜索封装
│  ├─ db.py                    # SQLite 建表与读写
│  └─ data/idioms.json         # 283 条习语 / 俚语 / 词组
├─ static/
│  ├─ index.html               # 单文件前端（原生 JS + CSS，无构建步骤）
│  └─ verify/                  # 搜索引擎所有权校验文件
├─ data/radar.db               # SQLite 数据库（已 .gitignore）
├─ deploy/                     # 云服务器部署套件（systemd / 备份 / 打包）
└─ docs/                       # 文档 + 自检脚本（清单见下方）
```

---

## 快速开始（本地）

```bash
git clone https://github.com/runlinxin-arch/info-radar.git
cd info-radar

# 1) 依赖
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS
pip install -r deploy/requirements.txt

# 2) 配置（必须，含 API key）
cp config.example.yaml config.yaml
# 编辑 config.yaml，填入 tavily.api_key（申请：https://tavily.com/）

# 3) 启动
python run.py                   # http://127.0.0.1:7100
```

首次启动会建表并立即抓取一次（因为无历史更新记录）。

---

## 配置

仓库里提供了 [`config.example.yaml`](config.example.yaml) 模板（不含任何密钥），复制为 `config.yaml` 后填入：

```yaml
tavily:
  api_key: "tvly-xxxx"        # 唯一需要自己申请的东西；留空则搜索接口不可用
  max_results: 10

llm:                           # 可选：点词解释优先走 OpenAI 兼容接口，失败回落词典
  provider: ""
  api_key: ""
  model: ""
  base_url: ""

per_section_keep: 30           # 每个板块保留多少条（超出即删除，无归档）
fetch_full_content: false      # ⚠️ 版权红线：保持 false，只抓摘要不抓全文

schedule:
  mode: "on_startup_and_periodic"
  min_interval_hours: 2
  periodic_hours: 4
  next_hint: "每 4 小时自动更新"

sources:                       # 信息源列表；enabled: false 保留配置但不抓取
  - name: "arXiv cs.AI"
    section: "学术 · AI/CS"
    type: rss
    url: "https://rss.arxiv.org/rss/cs.AI"
    enabled: true
```

> `tavily.api_key` 只出现在这个文件里，源码中零硬编码；`config.yaml` 已在 `.gitignore` 中。

---

## HTTP 接口

| 路径 | 说明 |
|---|---|
| `GET /` | 单页应用 |
| `GET /healthz` | 健康探针（`200` 新鲜 / `503` 停更 >8h），支持 HEAD |
| `GET /feed.xml` | RSS 2.0，最新 50 条（摘要 + 原文链接） |
| `GET /sitemap.xml` | 站点地图 |
| `GET /robots.txt` | 爬虫规则 + Sitemap 声明 |
| `GET /api/sections` | 板块与各自条数 |
| `GET /api/items?section=&limit=` | 条目列表（`limit ≤ 200`） |
| `GET /api/item/{id}` | 单条详情（含摘要） |
| `GET /api/search?q=` | Tavily 搜索（限流） |
| `GET /api/word?w=` | 点词解释（限流） |
| `GET /api/idioms` | 习语清单 |
| `GET /api/status` | 运行状态 / 更新日志 / 条目统计 |
| `POST /api/update` | 触发一次更新（限流） |

**限流规则**（内存态，单进程生效）：

| 规则 | 限制 |
|---|---|
| `/api/search` 单 IP | 10 次/分钟、50 次/天 |
| `/api/search` 全站 | 30 次/天（保护 Tavily 月额度） |
| `/api/word` 单 IP | 30 次/分钟 |
| `/api/update` 单 IP | 30 分钟 1 次 |

---

## 运维

| 场景 | 做法 |
|---|---|
| 启动 | `python run.py`（Windows 用 `pythonw` 无窗口运行） |
| 手动更新 | `python update.py` 或 `curl -X POST http://127.0.0.1:7100/api/update` |
| 看状态 | `python docs/audit/status_now.py` |
| 备份 | `bash deploy/backup.sh`（SQLite 在线备份，保留 14 天） |
| 日志 | `pythonw` 输出重定向到 `docs/audit/app-*.log`；云上走 `journalctl -u inforadar` |
| 部署到云服务器 | 见 [迁移指南.md](迁移指南.md) 与 [deploy/](deploy/) |
| 更新线上代码 | 服务器上 `bash deploy/deploy.sh`（备份 → 同步 → 装依赖 → 重启） |
| 监控 | UptimeRobot 每 5 分钟探 `/healthz`，见 [docs/监控接入.md](docs/监控接入.md) |

---

## 自检脚本

不依赖任何测试框架，全部是可直接运行的脚本，**退出码 0 = 通过**：

```bash
python docs/audit/status_now.py              # 运行状态快照
python docs/audit/test_feeds.py              # robots / sitemap / RSS（52 项）
python docs/audit/test_url_safety.py         # 外链协议白名单（32 项）
python docs/audit/test_rate_limit.py         # 限流语义与内存回收（21 项）
python docs/audit/test_healthz.py            # 健康探针（17 项）
python docs/audit/verify_report_claims.py    # 评审结论与代码一致性（23 条）
python docs/audit/verify_url_risk.py         # 协议防护前后对照实验
python docs/audit/verify_repo_completeness.py# 新克隆必需文件是否齐全
python docs/audit/verify_clone_works.py      # 新克隆能否真正加载词典
python docs/audit/check_healthz_live.py      # 线上探针验收（走公网）
python docs/audit/audit_live.py              # 线上体检（头信息 / 元信息 / 首屏）
python docs/audit/audit_code.py              # 源码审计（问题定位到行号）
python docs/audit/submit_indexnow.py [url]   # 向 Bing/Yandex 推送 URL
```

---

## 文档

| 文档 | 内容 |
|---|---|
| [docs/站点评审报告.md](docs/站点评审报告.md) | 完整的站点评审：问题分级、证据、修复状态、优先级路线图 |
| [迁移指南.md](迁移指南.md) | 从笔记本迁到云服务器的 10 步操作手册（含回滚） |
| [docs/监控接入.md](docs/监控接入.md) | `/healthz` 设计、UptimeRobot 配置、告警排查对照表 |
| [docs/SEO与分发接入.md](docs/SEO与分发接入.md) | robots / sitemap / RSS / IndexNow 的接入清单与踩坑记录 |
| [docs/deployment-progress.md](docs/deployment-progress.md) | 部署历史与交接备忘 |
| [docs/design-2026-08-24-improvements.md](docs/design-2026-08-24-improvements.md) | 早期设计改进记录 |
| [docs/handoff-frontend-polish.md](docs/handoff-frontend-polish.md) | 前端打磨交接说明 |

---

## 内容与版权声明

- 本站是**资讯聚合站**，不生产内容，也**不存储、不展示全文**。
- 所有条目的**著作权归原作者与原始发布方**；本站只展示摘要，并保留**原文链接与来源署名**。
- `fetch_full_content` 恒为 `false`（只抓 RSS 摘要，不抓正文）。
- 若你是权利人并认为本站展示方式侵犯了你的权益，请通过仓库 Issue 联系，我会在核实后移除相关条目。

**代码**：[MIT License](LICENSE) © 2026 runlinxin-arch —— 可自由使用、修改、分发、商用，保留版权声明即可。

> MIT **只覆盖代码**。本站聚合的文章标题、摘要、链接等内容**版权仍归各自发布方**，不在 MIT 授权范围内；
> 本项目对这类内容只做索引与摘要展示。

---

## 已知限制 / 路线图

| 限制 | 影响 | 计划 |
|---|---|---|
| 首页是单页应用，**首屏 HTML 无内容** | 搜索引擎抓到空壳，难以被索引 | 服务端渲染首页 |
| **内容无独立 URL**（详情是弹层） | 文章无法分享、收藏、被收录 | 新增 `/a/{id}` 服务端渲染文章页 |
| 每板块只留 **30 条**，超出即删 | 往期内容不可回溯 | 提高上限 + 归档表 |
| 抓取与 Web **同进程** | 抓取时可能拖慢响应 | 拆成独立进程 / systemd timer |
| **依赖单机常驻** | 关机关网即下线 | 迁移到云服务器（见迁移指南） |

完整的优先级路线图见 [docs/站点评审报告.md](docs/站点评审报告.md) 第九节。
