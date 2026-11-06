# SEO 与分发接入（任务 6 收尾清单）

> 代码侧已完成并上线。本文只讲**你还需要做什么**，以及哪些事现在做了也没用。
> 执行时间：约 15 分钟（不含搜索引擎审核）。

---

## 一、代码侧已完成（不需要你动手）

| 路径 | 内容 | 线上状态 |
|---|---|---|
| `/robots.txt` | 允许全站、屏蔽 `/api/` 与 `/healthz`、声明 `Sitemap:` | 200（源站内容正确） |
| `/sitemap.xml` | 站点地图，含首页 + `lastmod`（取自 `last_update`） | 200 |
| `/feed.xml` | RSS 2.0，最新 50 条，只含摘要 + 原文链接 + 来源 | 200，50 条真实条目 |

实现集中在 [app/feeds.py](../app/feeds.py)，路由在 [app/api.py](../app/api.py)。回归测试：`python docs\audit\test_feeds.py`（52 项）。

**RSS 现在就能用**：把它加进任何 RSS 阅读器（Feedly / Inoreader / NetNewsWire）即可订阅，不依赖搜索引擎。

---

## 二、你需要做的（按顺序）

### 1. 清一下 Cloudflare 的 `/robots.txt` 缓存（1 分钟，可选）

**现象**：源站 `robots.txt` 已经正确，但公网拿到的还是旧的、**不含 `Sitemap:` 行**的版本。

**原因**：Cloudflare 自己缓存 `robots.txt` 4 小时（`Cache-Control: max-age=14400`）。我实测时 `Age: 143`。

**处理**（二选一）：
- **等**：最多 4 小时自动生效，无需任何操作。
- **立刻**：Cloudflare 控制台 → 选中 `inforadar.xin` → **缓存 / Caching** → **配置 / Configuration** → **清除缓存 / Purge Cache** → **单个 URL** → 填 `https://inforadar.xin/robots.txt` → 清除。

> 不等也行：提交 sitemap 时可以手填 URL，不依赖 robots.txt 里的声明。但长期最好让爬虫能自动发现。

### 2. 提交 sitemap 给 Google（5 分钟）

1. 打开 <https://search.google.com/search-console>
2. **添加资源** → 选「**网址前缀**」→ 填 `https://inforadar.xin/`
3. 验证方式选 **DNS 记录**（Cloudflare 里加一条 TXT，最省事），或「HTML 标记」
4. 验证通过后 → 左侧 **索引 → 站点地图** → 提交 `sitemap.xml`
5. 顺手用「**网址检查**」输入 `https://inforadar.xin/` → 点「请求编入索引」

### 3. 提交给 Bing（3 分钟）

<https://www.bing.com/webmasters> → 支持**直接从 Google Search Console 导入**，一键搞定。
（Bing 的索引也会喂给 ChatGPT 搜索等下游，值得做。）

### 4. 做一个决策：要不要让百度收录

你现在这份 `robots.txt` 里，Cloudflare 的管理段包含：

```
User-agent: Baiduspider
Disallow: /
```

**百度爬虫被明确拒绝**。这大概不是你有意设置的（是 Cloudflare「Bot Preference Sync」的默认管理策略）。对一个面向中文读者的站来说，这是一个实实在在的流量决策。

- **想让百度收录**：Cloudflare 控制台 → **安全性 / Security → 设置 / Settings** → 筛选 **Bot traffic** → **AI Crawler and Agent access policies** → 调整 Search 策略 → 关掉相关的 **Bot Preference Sync** 或改策略 → 保存。
- **不在意百度**：什么都不用做，但要知道这是当前状态。

> 同理，`Google-Extended`、`GPTBot`、`ClaudeBot`、`KimiBot` 等 AI 训练爬虫也被拒。这是 Cloudflare 的默认「不允许 AI 训练」姿态，通常符合内容方利益，可以保留。

---

## 三、必须先说清楚的现实预期

**提交 sitemap ≠ 有流量。** 你现在有两件事没做，它们会直接决定搜索效果：

| 缺口 | 后果 |
|---|---|
| **首页是单页应用，首屏 HTML 只有「加载中…」**（P0-2） | Google 抓到的是一张空壳页，大概率报「已抓取，但当前未编入索引」。**这是预期结果，不是配置错误** |
| **sitemap 里只有 1 个 URL**（P0-1 未完成） | 站点没有文章级 URL 可提交。内容再多，对搜索也只有 1 个入口 |

所以**这一轮的真实产出是**：

- ✅ **RSS 订阅**：立刻可用，RSS 阅读器用户能订阅你 —— 这是现在唯一的真实分发渠道。
- ✅ **基础设施就位**：等 P0-1（`/a/{id}` 服务端渲染）做完，sitemap 和索引才有意义，那时不需要再改任何配置。
- ⚠️ **搜索结果**：短期内不会有明显变化，不要因为"提交了却没流量"而怀疑配置。

---

## 四、验证命令

```powershell
# 三个入口是否正常
curl.exe -s -o NUL -w "%{http_code}`n" https://inforadar.xin/robots.txt
curl.exe -s -o NUL -w "%{http_code}`n" https://inforadar.xin/sitemap.xml
curl.exe -s -o NUL -w "%{http_code}`n" https://inforadar.xin/feed.xml

# 公网 robots.txt 是否已经带上 Sitemap 行（缓存刷新后才会 true）
curl.exe -s https://inforadar.xin/robots.txt | Select-String "Sitemap:"

# 本地回归
python docs\audit\test_feeds.py
python docs\audit\verify_report_claims.py
```

---

## 五、下一步

做完这一轮，路线图上下一个真正值钱的是 **P0-1 + P0-2**：`/a/{id}` 服务端渲染的文章页 + `<head>` 里的 description / OG / canonical。

那一步完成后：
- sitemap 会从 1 个 URL 变成 N 个
- Google 抓到的首屏会有真实内容
- 分享到微信/Twitter 会有预览卡片

在此之前，搜索引擎相关的投入产出比都很低 —— **先把 RSS 发出去，让内容至少有一个流通渠道**。
