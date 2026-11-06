# PRD · P0：服务端渲染与文章页

| 项 | 值 |
|---|---|
| 版本 | v1.0 |
| 状态 | 待评审（含 3 个待拍板决策） |
| 日期 | 2026-11-06 |
| 对应里程碑 | M1（见 `InfoRadar-任务书-v3.md`） |
| 覆盖范围 | P0-1（文章 URL）/ P0-2（首屏与元信息）/ P0-3（内容归档） |

---

## 1. 背景与问题

### 1.1 三个事实

用实测数据说明为什么必须做这一轮：

**事实 1：内容活不过一个工作日**

| 板块 | 30 条覆盖的时间跨度 |
|---|---|
| 国内新闻 | **3.7 小时** |
| 世界新闻 | 11.5 小时 |
| 学术 · 交互设计 | 0.0 小时（同一批） |
| 学术 · AI/CS | 0.0 小时（同一批） |
| 学术 · 心理学 | 17.4 天 |
| AI 资讯 | 37.7 天（断更残留） |

最近 7 次更新平均新增 **111 条/次**，配 180 个展示位 → **单条寿命约 6.5 小时**。

**事实 2：每条内容没有地址**

详情是前端弹层（`.overlay`），URL 始终是 `/`。前端全文件 `pushState` 出现次数 = **0**。
用户读到一篇好文章，无法分享、无法收藏、无法被外部引用。

**事实 3：首屏是空的**

`GET /` 返回的 HTML 里，`<main>` 内只有：

```html
<div class="loading">加载中…</div>
```

`<h2>` 数量 0。配合 `<head>` 无 `description` / `og:*` / `canonical` / JSON-LD，
搜索引擎抓到的是一张空壳页；分享链接没有预览卡。

### 1.2 问题定性

> **这不是三个独立的功能缺失，而是同一个病的三个症状：站点不产生可积累的资产。**

- 时间不积累 → 没有历史
- 链接不积累 → 无法传播
- 索引不积累 → 无法被发现

且三者的依赖是**串行**的：P0-3 不做，P0-1 产出的链接活不过一天；P0-1 不做，P0-2 产出的 sitemap 只有一个 URL。

---

## 2. 目标与非目标

### 2.1 目标

| # | 目标 | 可度量 |
|---|---|---|
| G1 | 内容不再被物理删除，可回溯 | 归档表行数随更新单调增长；`items` 裁剪后归档等价保留 |
| G2 | 每条内容有稳定可分享的地址 | `GET /a/{id}` 返回 200 且 HTML 内嵌标题 |
| G3 | 首页首屏 HTML 含真实内容 | `curl /` 的 HTML 中 `<h2>` ≥ 30 |
| G4 | 分享有预览卡、可被索引 | `<head>` 含 og/canonical；sitemap URL 数 > 1 |

### 2.2 非目标（明确不做，防止范围膨胀）

| 不做 | 原因 |
|---|---|
| 全文抓取 / 站内全文阅读 | 版权红线，`fetch_full_content` 保持 `false` |
| 用户系统（登录/收藏/评论） | 与当前阶段无关 |
| 移动端重设计、可访问性全面整改 | P4，排在 M1 之后 |
| 归档浏览页 `/archive/{YYYY-MM}` | P1；P0 只保证数据不丢、URL 可直达 |
| 前端视觉改版 | 现有设计体系已验证，本轮不动 CSS 外观 |
| 抓取与 Web 进程拆分 | P3；本轮不改运行模型 |

---

## 3. 用户与场景

| 角色 | 场景 | 成功标准 |
|---|---|---|
| **读者** | 早上看到一条 AI 论文，晚上还想找回来 | 能从首页或存档找到，且链接仍有效 |
| **分享者** | 想把一条国内新闻发给朋友 | 复制 URL 即可，对方打开看到标题/摘要/原文入口 |
| **搜索引擎** | 抓取 `/` 与 sitemap | 拿到真实标题与摘要，并建立索引 |
| **站长（你）** | 一周后回看这周发生了什么 | 归档表里有完整记录，可按时间检索 |

---

## 4. 功能需求

### FR-1 · 内容归档（P0-3）

**描述**：裁剪不再删除，而是把超出保留额度的条目**搬运**到 `items_archive`，原 `id` 保持不变。

**规则**：
- 每次 `trim_section(section, keep)`：先插入归档，再删除活跃表中的超限行，**同一事务内完成**。
- 归档幂等：以 `link` 唯一。重复归档不报错（`INSERT OR IGNORE`）。
- 去重覆盖归档：`item_exists(link)` 必须同时查 `items` 与 `items_archive`，否则归档内容会在下次抓取时被当作新条目重新入库，导致 sitemap 重复 URL。

**验收**：
- 连续两次更新后，`SELECT COUNT(*) FROM items_archive` 单调增长
- `SELECT COUNT(*) FROM items WHERE is_search_result=0` 稳定在配置上限附近
- 归档中的 link 不会重新出现在 `items` 中

### FR-2 · 分板块保留额度（M0）

**描述**：`per_section_keep` 从单一整数改为「默认值 + 板块覆盖」。

**建议值**（决策 D1）：

| 板块 | 建议额度 | 理由 |
|---|---|---|
| 国内新闻 | 500 | 实测 30 条仅覆盖 3.7 小时，流速最快 |
| 世界新闻 | 300 | 11.5 小时 |
| AI 资讯 | 300 | 源少但更新慢 |
| 学术 ×3 | 300 | 每日批量，靠归档补历史 |

**配置形式**（向后兼容）：
```yaml
per_section_keep: 300
per_section_keep_override:
  国内新闻: 500
```

**验收**：下次更新后 `/api/status` 的 `feed_items` > 180。

### FR-3 · 文章页 `GET /a/{item_id}`（P0-1）

**描述**：服务端渲染单条内容，独立 URL，可直接打开。

**行为**：
- 先查 `items`，未命中查 `items_archive`；两处都没有 → **返回 HTTP 404 + HTML 404 页**（不是 JSON）。
- 内容：标题（`<h1>`）、来源、发布时间、摘要正文、原文链接、返回首页链接。
- `<head>`：`description`（摘要前 150 字）、`canonical`、`og:title/description/url/type=article`、`og:image`（站点默认图）。
- 页内 JSON-LD `Article`：headline / datePublished / dateModified / author(来源) / url。

**验收**：
- `/a/<存在的 id>` → 200，HTML 含 `<h1>` 与标题原文
- `/a/999999` → 404
- 归档中的 id 同样可访问（验证搬运后 URL 不失效）

### FR-4 · 首页服务端渲染（P0-2）

**描述**：`GET /` 的 HTML 首屏直接包含默认板块（AI 资讯）最新 30 条。

**实现方式（最小侵入）**：
- 保留现有 `static/index.html`（含全部 CSS/JS，不拆版式）
- 在 `<main id="content">` 内加一对占位标记：
  ```html
  <main id="content">
    <!-- SSR:START --><div class="loading">加载中…</div><!-- SSR:END -->
  </main>
  ```
- 服务端读取该文件，把两个标记之间的内容替换为**服务端渲染的卡片 HTML**
- CSS/JS 零改动

**卡片 HTML 规则**：字段与前端 `renderItems` 完全一致（标题、摘要、来源、时间、原文链接），所有文本经 HTML 转义；外链再过一次协议白名单（复用 `crawler.safe_link`）。

**验收**：`curl /` 的 HTML 中 `<h2>` ≥ 30；无 JS 环境下也能看到内容。

### FR-5 · 前端水合（P0-2 配套）

**描述**：SSR 后，前端首次加载不得重渲染首屏。

**规则**：
- `init()` 中，若 `<main>` 内已存在 `.card` 元素 → **跳过首次 `loadItems()`**，但仍执行 `loadSections()` 以填充标签计数。
- 切换板块时走原有 fetch 流程（行为不变）。

**验收**：首屏无「内容闪一下再重绘」；Network 面板首次加载没有 `/api/items` 请求。

### FR-6 · 首页 `<head>` 元信息（P0-2）

**描述**：首页 meta 是静态的，直接写进 `static/index.html` 的 `<head>`，无需服务端渲染。

**内容**：
- `description`：站点一句话介绍（≤ 100 字）
- `<link rel="canonical" href="https://inforadar.xin/">`
- `og:type=website`、`og:site_name`、`og:title`、`og:description`、`og:url`、`og:image`
- `twitter:card=summary_large_image`
- `meta name="robots" content="index,follow"`
- `theme-color`
- 已有：`favicon`（本轮补 `static/og.png` 1200×630）

**验收**：页面源码含上述全部标签；OG 调试器能取到图。

### FR-7 · sitemap 扩容（P0-1/P0-2 收尾）

**描述**：`/sitemap.xml` 从「只有首页」扩展为「首页 + 文章 URL」。

**规则**：
- 收录顺序：活跃 `items` → `items_archive`，按 `published_at` 倒序
- 上限：单文件最多 **5000** 条（低于协议上限 50000，留出未来扩容与性能余量）
- 每条含 `<loc>` 与 `<lastmod>`（`published_at` 或 `fetched_at` 的日期部分）
- 超出上限的部分：P1 用 sitemap index 分片

**验收**：sitemap 解析后 URL 数 ≥ 30；`test_feeds.py` 中「恰好 1 个 url」的断言需同步更新。

### FR-8 · 404 页面（P0-1 配套）

**描述**：`/a/{不存在}` 与未知路径返回 HTML 404（当前未知路径返回 JSON `{"detail":"Not Found"}`）。

**规则**：保持现有 `/api/*` 的 JSON 404 不变，仅对**页面类路由**返回 HTML 404。

**验收**：浏览器打开 `/a/999999` 看到可读的 404 页，而非 JSON。

---

## 5. 非功能需求

| 类别 | 要求 |
|---|---|
| 性能 | SSR 首页服务端耗时 < 50 ms（本地 SQLite，1–2 次查询） |
| 缓存 | 首页 `Cache-Control: public, max-age=60`；文章页 `public, max-age=300`；`/healthz` 保持不缓存 |
| SEO | 每个页面仅一个 `<h1>`；canonical 自指；`robots` 不阻断 |
| 安全 | 所有动态文本 HTML 转义；外链过 `safe_link`；`/a/{id}` 的 id 必须为整数 |
| 可观测 | 新增 `docs/audit/test_ssr.py`，纳入回归套件 |
| 向后兼容 | `/api/*` 行为与返回结构不变；`/healthz` 不变 |
| 数据库 | 迁移必须幂等、可重复执行；先建表后搬运，失败可回滚 |

---

## 6. 数据模型变更

### 6.1 新表

```sql
CREATE TABLE IF NOT EXISTS items_archive (
    id          INTEGER PRIMARY KEY,      -- 与 items.id 保持一致，保证 /a/{id} 不失效
    title       TEXT NOT NULL,
    summary     TEXT,
    content     TEXT,
    link        TEXT NOT NULL,
    source      TEXT,
    section     TEXT NOT NULL,
    published_at TEXT,
    fetched_at  TEXT NOT NULL,
    archived_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_archive_link ON items_archive(link);
CREATE INDEX IF NOT EXISTS idx_archive_section ON items_archive(section, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_archive_pub ON items_archive(published_at DESC);
```

### 6.2 关键约束

| 约束 | 理由 |
|---|---|
| `id` 搬运不变 | `/a/{id}` 与已分享链接永久有效 |
| `link` 唯一 | 归档幂等；防止 sitemap 出现重复 URL |
| `item_exists()` 查两表 | 否则归档内容会被重新抓回 `items` |
| `items.AUTOINCREMENT` 不重置 | 防止新条目复用归档 id |
| 搬运在同一事务 | 避免「已删未归档」的数据丢失窗口 |

### 6.3 迁移方式

`init_db()` 中新增 `items_archive` 建表（`IF NOT EXISTS`，幂等）。
本轮**不搬历史数据**（当前只有 180 条活跃，历史已丢失无法恢复）；归档表从本轮上线后开始增长。

> 若要补历史：无法补（已删除）。这是 P0-3 拖到今天才做的既成代价。

---

## 7. 技术方案

### 7.1 模板层选型（混合，控制风险）

| 页面 | 方案 | 理由 |
|---|---|---|
| 首页 | **占位标记注入**（读 `static/index.html` 后字符串替换） | CSS/JS 是调试好的单文件结构，拆模板回归风险高 |
| 文章页 | **Jinja2 模板**（`app/templates/article.html`） | 新页面，模板化利于后续归档页扩展 |

> Jinja2 本机已安装（3.1.6），但**不在 `deploy/requirements.txt`** 中 ——
> 它只是被其他包带进来的。必须显式加入依赖，否则云上部署会 `ModuleNotFoundError`。

### 7.2 新增/修改文件

| 文件 | 变更 |
|---|---|
| `app/db.py` | 新增 `items_archive` 建表、`archive_items()`、`get_item_any()`；`item_exists()` 查两表；`trim_section()` 改为搬运 |
| `app/render.py`（新） | `render_cards(items)`、`render_index_html(items)`；Jinja2 环境与模板加载 |
| `app/templates/article.html`（新） | 文章页模板（含 meta + JSON-LD） |
| `app/templates/404.html`（新） | 404 页 |
| `app/api.py` | `index()` 改为 SSR；新增 `/a/{id}`；页面类 404 改 HTML |
| `app/feeds.py` | `render_sitemap()` 接收文章列表，扩容 |
| `static/index.html` | `<main>` 加 SSR 占位标记；`<head>` 补 meta；`init()` 加水合判断 |
| `static/og.png`（新） | 1200×630 默认分享图 |
| `config.yaml` / `config.example.yaml` | `per_section_keep` + `per_section_keep_override` |
| `deploy/requirements.txt` | 加 `jinja2>=3.1,<4.0` |
| `docs/audit/test_ssr.py`（新） | 本轮验收脚本 |

### 7.3 请求流程（改造后）

```
GET /                      → 读 static/index.html → 注入首屏 30 条卡片 → 返回 HTML
                             浏览器执行 JS → init() 发现已有 .card → 跳过首次 loadItems()
GET /a/{id}                → 查 items → miss 查 items_archive → 渲染 article.html
                             → miss 两者 → HTML 404
GET /sitemap.xml           → 首页 + 活跃文章 + 归档文章（≤5000）
GET /api/items?section=    → 行为不变（前端切板块仍走它）
```

### 7.4 前端水合伪代码

```javascript
async function init() {
  const hasSSR = document.querySelector('#content .card') !== null;
  await loadSections();               // 标签计数仍需 API
  if (!hasSSR) loadItems();           // 只有未 SSR 时才拉首屏
  const d = await (await fetch('/api/status')).json();
  renderStatus(d);
  if (d.running) pollStatus();
}
```

---

## 8. URL 与信息架构

| URL | 说明 | 本轮 |
|---|---|---|
| `/` | 首页（默认 AI 资讯） | 改 SSR |
| `/?s={板块}` | 板块直达（依赖前端 pushState） | 可选增强 |
| `/a/{id}` | 文章页 | **新增** |
| `/archive/{YYYY-MM}` | 归档浏览 | P1 |
| `/sitemap.xml` | 站点地图（扩容） | 改 |
| `/feed.xml` | RSS 50 条 | 不变 |
| `/healthz` | 探针 | 不变 |

---

## 9. 任务拆分

| ID | 任务 | 依赖 | 工时 |
|---|---|---|---|
| TSK-01 | `items_archive` 建表 + 索引 + 迁移幂等 | — | 1h |
| TSK-02 | `trim_section` 改为搬运；`item_exists` 查两表；`get_item_any` | TSK-01 | 2h |
| TSK-03 | 分板块 keep 配置解析（含向后兼容） | — | 0.5h |
| TSK-04 | `app/render.py`：卡片 HTML 渲染 + 首页占位注入 | TSK-02 | 2h |
| TSK-05 | `static/index.html`：SSR 占位标记 + 水合判断 | TSK-04 | 1h |
| TSK-06 | 首页 `<head>` 静态 meta + `static/og.png` | — | 1.5h |
| TSK-07 | `/a/{id}` 路由 + `article.html` 模板 + JSON-LD + HTML 404 | TSK-02 | 3h |
| TSK-08 | sitemap 扩容（含 `test_feeds.py` 断言更新） | TSK-01 | 1h |
| TSK-09 | `docs/audit/test_ssr.py`（≥15 项） | TSK-04~08 | 2h |
| TSK-10 | 更新 `verify_report_claims.py`、任务书、评审报告状态 | 全部 | 1h |

**合计约 15 小时 ≈ 2 个工作日。**

关键路径：TSK-01 → TSK-02 → TSK-07（文章页）/ TSK-04（首页 SSR）。TSK-03、TSK-06 可并行。

---

## 10. 验收标准

### 10.1 机器验证（必须全绿）

```powershell
# 首页有真实内容
curl.exe -s https://inforadar.xin/ | Select-String '<h2>' | Measure-Object | % Count   # ≥ 30

# 文章页可直达（id 取当前存在的一条）
curl.exe -s -o NUL -w "%{http_code}" https://inforadar.xin/a/<id>                      # 200
curl.exe -s -o NUL -w "%{http_code}" https://inforadar.xin/a/999999                    # 404

# 元信息
curl.exe -s https://inforadar.xin/ | Select-String 'og:title|canonical|og:image'

# sitemap 扩容
(Invoke-RestMethod https://inforadar.xin/sitemap.xml).Count                             # > 1

# 回归
python docs\audit\test_ssr.py            # 新增，退出码 0
python docs\audit\test_feeds.py          # 退出码 0
python docs\audit\verify_report_claims.py # 退出码 0
python docs\audit\check_healthz_live.py  # 退出码 0
```

### 10.2 人工验证

- 手机浏览器打开 `/a/<id>`，链接可分享、微信/Twitter 有预览卡
- 关掉 JavaScript 后打开 `/`，仍能看到 30 条内容
- GSC「网址检查」显示首页已含正文（不再是空壳）

---

## 11. 回滚方案

| 风险点 | 回滚动作 |
|---|---|
| SSR 首页出错 | 把 `index()` 改回 `FileResponse(static/index.html)`（占位标记内保留原「加载中」内容，天然降级） |
| 归档搬运写错 | `trim_section` 恢复为纯 DELETE（`items_archive` 保留，不丢已有归档） |
| 文章页模板异常 | 摘掉 `/a/{id}` 路由即可，不影响其他页面 |
| 整体回滚 | `git revert` 对应提交 + 重启（一次 `systemctl restart` 或重启 pythonw） |

> 设计上已保证**渐进降级**：SSR 失败 = 退回当前 SPA 行为，不会白屏。

---

## 12. 开放问题（需拍板）

| # | 问题 | 建议 | 若选备选的影响 |
|---|---|---|---|
| D1 | 分板块保留额度 | 国内 500 / 世界 300 / AI 300 / 学术 300 | 统一 300：国内新闻仍会 4h 一洗 |
| D2 | 归档浏览页 | 排 P1（本轮只做数据 + sitemap） | 本轮做：+1 天工时 |
| D3 | 精读/全文 | 保持 false；无正文条目隐藏入口、改名「预览」；授权源白名单 P1 | 砍功能：前端删 ~80 行 |
| D4 | `/a/{id}` 是否允许索引 | **允许**（`index,follow`），是本轮 SEO 目标 | 不索引则 PRD 目标 G4 失效 |
| D5 | 是否顺带修「量子位」遗留源（config 非唯一事实来源） | **同一批修**：以 config 为准，DB 中未列出的源置 disabled | 不修：每轮多抓 1 个源、日志持续出现 `partial` 噪音 |
