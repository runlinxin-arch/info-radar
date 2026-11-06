# -*- coding: utf-8 -*-
"""任务 6 回归测试：robots.txt / sitemap.xml / feed.xml。

分两层：
  1. 纯函数层（app.feeds）——输出结构、XML 转义、时间格式、脏数据兜底
  2. 路由层（TestClient）——状态码、Content-Type、真实数据库内容

用法： python docs/audit/test_feeds.py
退出码 0 = 全部通过
"""
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

from app import feeds  # noqa: E402
from app.feeds import (  # noqa: E402
    SITE_URL,
    iso_date,
    render_robots,
    render_rss,
    render_sitemap,
    rfc822,
)

failed = 0
total = 0


def check(desc, ok, extra=""):
    global failed, total
    total += 1
    if not ok:
        failed += 1
    print(f"  [{'通过' if ok else '失败'}] {desc}{extra}")
    return ok


RSS_DATE = re.compile(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} "
                      r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
                      r"\d{4} \d{2}:\d{2}:\d{2} \+0800$")

# ------------------------------------------------------------------ robots.txt
print("=" * 76)
print("1. robots.txt")
print("=" * 76)
robots = render_robots()
check("包含 User-agent: *", "User-agent: *" in robots)
check("允许根路径 Allow: /", "Allow: /" in robots)
check("屏蔽 API（Disallow: /api/）", "Disallow: /api/" in robots)
check("屏蔽探针（Disallow: /healthz）", "Disallow: /healthz" in robots)
check("声明 Sitemap 且指向 sitemap.xml",
      f"Sitemap: {SITE_URL}/sitemap.xml" in robots)
check("不重复 Cloudflare 管理段（避免拼接后出现两份）",
      "BEGIN Cloudflare Managed content" not in robots
      and "Content-Signal" not in robots)
check("以换行结尾", robots.endswith("\n"))

# ----------------------------------------------------------------- sitemap.xml
print()
print("=" * 76)
print("2. sitemap.xml")
print("=" * 76)
sitemap = render_sitemap("2026-11-06 08:22:00")
try:
    root = ET.fromstring(sitemap)
    parsed = True
except ET.ParseError as exc:
    root = None
    parsed = False
    print(f"        解析失败：{exc}")
check("是合法 XML", parsed)

if parsed:
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    check("根元素为 urlset", root.tag == f"{ns}urlset", f"（{root.tag}）")
    urls = root.findall(f"{ns}url")
    check("恰好 1 个 <url>（单页应用，暂无文章级 URL）", len(urls) == 1,
          f"（实际 {len(urls)}）")
    if urls:
        loc = urls[0].find(f"{ns}loc")
        lastmod = urls[0].find(f"{ns}lastmod")
        check("loc 指向站点根", loc is not None and loc.text == f"{SITE_URL}/",
              f"（{loc.text if loc is not None else None}）")
        check("lastmod 为 W3C 日期格式",
              lastmod is not None and re.fullmatch(r"\d{4}-\d{2}-\d{2}",
                                                  lastmod.text or "") is not None,
              f"（{lastmod.text if lastmod is not None else None}）")
        check("lastmod 取的是 last_update 的日期",
              lastmod is not None and lastmod.text == "2026-11-06")
        check("没有塞 /?s= 之类的重复内容 URL",
              all("?s=" not in (u.find(f"{ns}loc").text or "") for u in urls))

# 无 last_update 时仍应合法
try:
    ET.fromstring(render_sitemap(None))
    no_last_ok = True
except ET.ParseError:
    no_last_ok = False
check("last_update 缺失时仍是合法 XML", no_last_ok)
check("last_update 缺失时不输出 lastmod",
      "<lastmod>" not in render_sitemap(None))

check("iso_date 正常转换", iso_date("2026-11-06 08:22:00") == "2026-11-06")
check("iso_date 对脏数据返回 None", iso_date("not-a-date") is None)

# ------------------------------------------------------------------ 时间格式
print()
print("=" * 76)
print("3. RFC 822 时间（RSS 2.0 要求，且不能受系统 locale 影响）")
print("=" * 76)
got = rfc822("2026-11-06 12:00:00")
check("2026-11-06 是周五（Fri）", got == "Fri, 06 Nov 2026 12:00:00 +0800", f"（{got!r}）")
check("符合 RFC 822 格式", bool(RSS_DATE.match(got or "")))
check("纯 ASCII（中文 Windows 的 strftime 会输出「周五」）",
      (got or "").isascii())
check("带 +0800 时区", (got or "").endswith("+0800"))
check("非法输入返回 None", rfc822("garbage") is None)
check("None 返回 None", rfc822(None) is None)

# -------------------------------------------------------------------- feed.xml
print()
print("=" * 76)
print("4. RSS 渲染：转义、脏数据、边界")
print("=" * 76)
SAMPLE = [
    {"title": "正常标题", "summary": "正常摘要", "link": "https://example.com/a",
     "source": "示例源", "section": "AI 资讯",
     "published_at": "2026-11-06 08:00:00", "fetched_at": "2026-11-06 08:22:00"},
    {"title": "<script>alert('x')</script> & A&B", "summary": '引号"与\'单引号\'',
     "link": "https://example.com/b", "source": "危险标题源", "section": "世界新闻",
     "published_at": "2026-11-05 10:00:00", "fetched_at": "2026-11-06 08:22:00"},
    {"title": "带控制字符", "summary": "摘要含\x0b非法字符\x07", "link": "https://example.com/c",
     "source": "源C", "section": "国内新闻",
     "published_at": None, "fetched_at": "2026-11-06 08:22:00"},
    {"title": "非法协议应被排除", "summary": "x", "link": "javascript:alert(1)",
     "source": "源D", "section": "AI 资讯",
     "published_at": "2026-11-06 08:00:00", "fetched_at": "2026-11-06 08:22:00"},
]
rss = render_rss(SAMPLE, "2026-11-06 08:22:00")
try:
    rroot = ET.fromstring(rss)
    rss_ok = True
except ET.ParseError as exc:
    rroot = None
    rss_ok = False
    print(f"        解析失败：{exc}")
check("是合法 XML", rss_ok)

if rss_ok:
    items = rroot.findall("./channel/item")
    check("javascript: 链接被排除（3 条入库）", len(items) == 3, f"（实际 {len(items)}）")
    titles = [i.findtext("title") for i in items]
    check("<script> 标题被转义后仍能原样还原",
          "<script>alert('x')</script> & A&B" in titles,
          f"（{titles[:2]}）")
    check("没有真实的 <script> 元素（说明转义生效）",
          not rss.lower().count("<script"))
    check("控制字符被剔除",
          all("\x0b" not in (i.findtext("summary") or "") for i in items))
    check("每条都有 link 且为 http(s)",
          all((i.findtext("link") or "").startswith("http") for i in items))
    check("guid 标记 isPermaLink=true",
          all(i.find("guid") is not None
              and i.find("guid").get("isPermaLink") == "true" for i in items))
    check("description 带来源标注",
          any((i.findtext("description") or "").startswith("[示例源]") for i in items))
    check("有 pubDate 的条目时间格式正确",
          all(RSS_DATE.match(i.findtext("pubDate") or "")
              for i in items if i.findtext("pubDate") is not None))
    check("缺 published_at 的条目回落到 fetched_at",
          any(i.findtext("title") == "带控制字符" and i.findtext("pubDate") for i in items))
    check("channel 有 title/link/description/language",
          all(rroot.find(f"./channel/{t}") is not None
              for t in ("title", "link", "description", "language")))
    check("lastBuildDate 取自传入值",
          rroot.findtext("./channel/lastBuildDate") == "Fri, 06 Nov 2026 08:22:00 +0800",
          f"（{rroot.findtext('./channel/lastBuildDate')}）")

empty_rss = render_rss([], None)
try:
    ET.fromstring(empty_rss)
    empty_ok = True
except ET.ParseError:
    empty_ok = False
check("空列表仍输出合法 XML", empty_ok)
check("空列表没有 item", "<item>" not in empty_rss)

# ------------------------------------------------------------------ 路由层
print()
print("=" * 76)
print("5. 路由层（TestClient，读真实数据库）")
print("=" * 76)
try:
    from fastapi.testclient import TestClient
    from app.api import app

    client = TestClient(app)

    r = client.get("/robots.txt")
    check("/robots.txt 200", r.status_code == 200, f"（{r.status_code}）")
    check("/robots.txt Content-Type 为 text/plain",
          "text/plain" in r.headers.get("content-type", ""),
          f"（{r.headers.get('content-type')}）")
    check("/robots.txt 含 Sitemap 行",
          f"Sitemap: {SITE_URL}/sitemap.xml" in r.text)
    check("/robots.txt 可缓存",
          "public" in r.headers.get("cache-control", ""))

    r = client.get("/sitemap.xml")
    check("/sitemap.xml 200", r.status_code == 200, f"（{r.status_code}）")
    check("/sitemap.xml Content-Type 为 xml",
          "xml" in r.headers.get("content-type", ""),
          f"（{r.headers.get('content-type')}）")
    try:
        ET.fromstring(r.text)
        sm_ok = True
    except ET.ParseError:
        sm_ok = False
    check("/sitemap.xml 可解析", sm_ok)

    r = client.get("/feed.xml")
    check("/feed.xml 200", r.status_code == 200, f"（{r.status_code}）")
    check("/feed.xml Content-Type 为 rss+xml",
          "rss+xml" in r.headers.get("content-type", ""),
          f"（{r.headers.get('content-type')}）")
    try:
        froot = ET.fromstring(r.text)
        feed_ok = True
    except ET.ParseError:
        feed_ok = False
    check("/feed.xml 可解析", feed_ok)
    if feed_ok:
        live_items = froot.findall("./channel/item")
        check("真实数据里有条目", len(live_items) > 0, f"（{len(live_items)} 条）")
        check("条目数不超过 FEED_LIMIT",
              len(live_items) <= feeds.FEED_LIMIT, f"（上限 {feeds.FEED_LIMIT}）")
        check("所有 link 都是 http(s)（历史脏数据已过滤）",
              all((i.findtext("link") or "").startswith("http") for i in live_items))
        check("每条都有 title",
              all((i.findtext("title") or "").strip() for i in live_items))
except ImportError as exc:
    print(f"  [跳过] 缺少 TestClient：{exc}")

print()
print(f"合计 {total} 项，失败 {failed} 项。")
sys.exit(1 if failed else 0)
