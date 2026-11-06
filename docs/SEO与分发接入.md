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

## 二、进度与剩余动作

### 1. Cloudflare `/robots.txt` 缓存 —— ✅ 已完成（自动生效，无需操作）

**当时的现象**：源站 `robots.txt` 已正确，但公网拿到的还是旧的、**不含 `Sitemap:` 行**的版本（Cloudflare 缓存 4 小时，`max-age=14400`）。

**最终结果**：缓存已自然刷新，实测公网 `robots.txt` 已包含：

```
Sitemap: https://inforadar.xin/sitemap.xml
```

不需要清缓存了。**此项已闭环。**

### 2. 提交 sitemap 给 Google —— ✅ 已完成（2026-11-06）

必须登录**你自己的 Google 账号**才能创建 Search Console 资源，这一步没有免登录的办法（Google 没有 IndexNow 之类的开放提交协议）。

1. 打开 <https://search.google.com/search-console>
2. **添加资源** → 选「**网址前缀**」→ 填 `https://inforadar.xin/`
3. 验证方式选「**HTML 文件**」—— **已就绪，直接点「验证」即可**
4. 验证通过后 → 左侧 **索引 → 站点地图** → 提交 `sitemap.xml`
5. 顺手用「**网址检查**」输入 `https://inforadar.xin/` → 点「请求编入索引」

**提交时踩过的两个坑（都出在输入框，不是服务端）**：

| 填了什么 | GSC 实际去抓的 | 结果 |
|---|---|---|
| 留空 / 只填 `/` | `https://inforadar.xin/` | 「**Sitemap 是 HTML**」（抓到首页，第 2 行是 `<html>`） |
| `inforadar.xin/sitemap.xml` | `https://inforadar.xin/inforadar.xin/sitemap.xml` | 404「**无法读取此站点地图**」 |
| **`sitemap.xml`** ✅ | `https://inforadar.xin/sitemap.xml` | **成功** |

> 输入框左侧的 `inforadar.xin/` 是 GSC 自带前缀，**只补后面那一段**，不要带协议、不要带域名、不要带前导斜杠。

**验证文件（已部署）**：

| 项 | 值 |
|---|---|
| 路径 | `https://inforadar.xin/google6e1f8eda28d0a5ad.html` |
| 内容 | `google-site-verification: google6e1f8eda28d0a5ad.html`（53 字节，无换行） |
| 状态 | HTTP **200**，用 Googlebot UA 实测同样 200 |
| 源文件位置 | `static/verify/`（后续 GSC 换文件时，丢进去即可生效，无需改代码） |

> 若你更想用 DNS 方式：在 Cloudflare 加一条 TXT 即可，两种方式等效。但 HTML 文件已经放好了，少一步。
>
> ⚠️ **验证通过后不要删这个文件** —— GSC 会定期复查，文件消失会导致所有权失效。

> 已验证前置条件全部就绪（否则你会在最后白等）：
> Googlebot UA 取 `/`、`/robots.txt`、`/sitemap.xml` **全部 200**；无 `X-Robots-Tag` 阻断头；无 `noindex`。

### 3. 提交给 Bing —— ✅ 已通过 IndexNow 完成（无需登录）

**已完成**：走 [IndexNow](https://www.indexnow.org/) 协议提交，返回 **HTTP 202 Accepted**。

- 校验文件：`https://inforadar.xin/6c1251d53cc84103413cf3db781d93f0.txt`
- 提交脚本：`python docs\audit\submit_indexnow.py [url...]`
- IndexNow 会把 URL 分发给 Bing、Yandex、Seznam、Naver 等参与方

**仍可选的加分项**（需要登录，但只影响"能看到数据"，不影响"已提交"）：

<https://www.bing.com/webmasters> → 可直接**从 Google Search Console 导入**（建议等第 2 步做完再导）。
Bing 后台能看到抓取状态和索引量；Bing 的索引也会喂给 ChatGPT 搜索等下游。

> 后续每次有新内容要推送时，运行 `python docs\audit\submit_indexnow.py <url>` 即可。
> 目前只有一个可提交 URL `/`，等 P0-1（`/a/{id}`）落地后这个脚本才真正有用。

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

# 公网 robots.txt 是否已带上 Sitemap 行（现已生效）
curl.exe -s https://inforadar.xin/robots.txt | Select-String "Sitemap:"

# IndexNow 校验文件
curl.exe -s -o NUL -w "%{http_code}`n" https://inforadar.xin/6c1251d53cc84103413cf3db781d93f0.txt

# 用搜索引擎的 UA 自测（排除被 Cloudflare 拦的可能）
curl.exe -s -o NUL -w "%{http_code}`n" -A "Mozilla/5.0 (compatible; Googlebot/2.1)" https://inforadar.xin/
curl.exe -s -o NUL -w "%{http_code}`n" -A "Mozilla/5.0 (compatible; bingbot/2.0)" https://inforadar.xin/

# 重新推送 URL 给 IndexNow（有新内容时用）
python docs\audit\submit_indexnow.py https://inforadar.xin/

# 本地回归
python docs\audit\test_feeds.py
python docs\audit\verify_report_claims.py
```

> 注意：Cloudflare 会拦裸 `Python-urllib` 的 UA（返回 403），自测时记得带 `-A`。

---

## 五、下一步

做完这一轮，路线图上下一个真正值钱的是 **P0-1 + P0-2**：`/a/{id}` 服务端渲染的文章页 + `<head>` 里的 description / OG / canonical。

那一步完成后：
- sitemap 会从 1 个 URL 变成 N 个
- Google 抓到的首屏会有真实内容
- 分享到微信/Twitter 会有预览卡片

在此之前，搜索引擎相关的投入产出比都很低 —— **先把 RSS 发出去，让内容至少有一个流通渠道**。
