# -*- coding: utf-8 -*-
"""robots.txt / sitemap.xml / RSS 订阅源 的纯渲染函数。

集中成一层的理由：三件事本质相同——把数据库内容变成文本，与路由无关，
抽出来就能脱离 HTTP 单测（见 docs/audit/test_feeds.py）。

设计取舍：
- 站点当前是单页应用，没有文章级 URL（P0-1 未完成），所以 sitemap 只能
  诚实列出首页；等 /a/{id} 上线后再往里加。
- RSS 用 summary 而不是 content，维持「只出摘要 + 原文链接」的版权红线。
- 所有外链都要再过一次 safe_link：数据库里可能还躺着白名单上线前入库的
  历史行，渲染期再校验一遍是纵深防御。
"""
import re
from datetime import datetime
from xml.sax.saxutils import escape

from .crawler import safe_link

SITE_URL = "https://inforadar.xin"
SITE_NAME = "InfoRadar · 个人资讯雷达"
SITE_DESC = "AI 资讯 / 世界与国内新闻 / arXiv 学术，自动更新；只提供摘要与原文链接。"
FEED_LIMIT = 50
TZ_OFFSET = "+0800"   # 站点面向中文读者，发布时间统一按北京时间输出

# XML 1.0 不允许的控制字符：抓来的摘要里偶尔会混进 \x0b 之类，直接剔除
_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# strftime 的 %a/%b 受系统 locale 影响（中文 Windows 会输出「周一」），
# RFC 822 要求英文缩写，所以自己拼，不依赖 locale。
_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _clean(text):
    return _ILLEGAL_XML.sub("", str(text or ""))


def _xml(text):
    """先剔除非法字符再转义。"""
    return escape(_clean(text))


def _parse_dt(value):
    """解析数据库里的时间串，失败返回 None。"""
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value).strip()[:19], fmt)
        except (TypeError, ValueError):
            continue
    return None


def rfc822(value):
    """转成 RFC 822 时间（RSS 2.0 要求），解析失败返回 None。"""
    dt = _parse_dt(value)
    if dt is None:
        return None
    return (f"{_DAYS[dt.weekday()]}, {dt.day:02d} {_MONTHS[dt.month - 1]} "
            f"{dt.year:04d} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d} {TZ_OFFSET}")


def iso_date(value):
    """转成 sitemap 用到的 W3C 日期（YYYY-MM-DD），失败返回 None。"""
    dt = _parse_dt(value)
    return dt.strftime("%Y-%m-%d") if dt else None


# ---------------------------------------------------------------- robots.txt
def render_robots():
    """站点自身的 robots.txt。

    注意：Cloudflare 的「Bot Preference Sync」开启时，会把它的 Managed content
    **前置拼接到本站这份内容之前**（官方文档：origin 返回 200 才会合并）。
    所以这里只写站点自己的规则，不要重复 CF 的管理段。
    """
    return (
        "# InfoRadar\n"
        "# 说明：Cloudflare 可能在本文件之前拼接其 Managed content（内容信号策略），\n"
        "#       本段是站点自身规则，会追加在其后生效。\n"
        "\n"
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /healthz\n"
        "\n"
        f"Sitemap: {SITE_URL}/sitemap.xml\n"
    )


# --------------------------------------------------------------- sitemap.xml
def render_sitemap(last_update=None):
    """站点地图。

    当前只有一个可索引 URL：首页。文章级 URL 要等 /a/{id} 落地（P0-1），
    在那之前往 sitemap 里塞 /?s=xxx 只会制造重复内容。
    """
    lastmod = iso_date(last_update)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        "  <!-- 文章级 URL 待 P0-1（服务端渲染 /a/{id}）实现后加入 -->",
        "  <url>",
        f"    <loc>{SITE_URL}/</loc>",
    ]
    if lastmod:
        lines.append(f"    <lastmod>{lastmod}</lastmod>")
    lines += [
        "    <changefreq>hourly</changefreq>",
        "    <priority>1.0</priority>",
        "  </url>",
        "</urlset>",
    ]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ feed.xml
def render_rss(items, last_build=None):
    """RSS 2.0。只输出摘要与原文链接，不放正文。"""
    build_dt = rfc822(last_build) or rfc822(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        "  <channel>",
        f"    <title>{_xml(SITE_NAME)}</title>",
        f"    <link>{SITE_URL}/</link>",
        f"    <description>{_xml(SITE_DESC)}</description>",
        "    <language>zh-CN</language>",
        "    <ttl>60</ttl>",
    ]
    if build_dt:
        out.append(f"    <lastBuildDate>{build_dt}</lastBuildDate>")

    for it in items or []:
        link = safe_link(it.get("link"))
        if not link:
            continue   # 历史脏数据兜底：非法协议不进入订阅源
        title = _clean(it.get("title") or "(无标题)")
        summary = _clean(it.get("summary") or "")
        source = _clean(it.get("source") or "")
        section = _clean(it.get("section") or "")
        desc = f"[{source}] {summary}" if source and summary else summary

        out.append("    <item>")
        out.append(f"      <title>{_xml(title)}</title>")
        out.append(f"      <link>{_xml(link)}</link>")
        out.append(f'      <guid isPermaLink="true">{_xml(link)}</guid>')
        pub = rfc822(it.get("published_at") or it.get("fetched_at"))
        if pub:
            out.append(f"      <pubDate>{pub}</pubDate>")
        if section:
            out.append(f"      <category>{_xml(section)}</category>")
        if desc:
            out.append(f"      <description>{_xml(desc)}</description>")
        out.append("    </item>")

    out += ["  </channel>", "</rss>"]
    return "\n".join(out) + "\n"
