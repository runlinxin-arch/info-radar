# -*- coding: utf-8 -*-
"""RSS 抓取 + trafilatura 网页正文提取。"""
import logging
import time

import feedparser
import requests
import trafilatura

from . import processor

log = logging.getLogger("crawler")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) InfoRadar/1.0"}


def fetch_feed(url, timeout=20):
    """返回条目列表：[{title, link, summary, published_at}]，失败返回 None。"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        feed = feedparser.parse(r.content)
        entries = []
        for e in feed.entries:
            title = (e.get("title") or "").strip()
            link = (e.get("link") or "").strip()
            if not title or not link:
                continue
            summary = e.get("summary") or e.get("description") or ""
            published = None
            parsed = e.get("published_parsed") or e.get("updated_parsed")
            if parsed:
                try:
                    published = time.strftime("%Y-%m-%d %H:%M:%S", parsed)
                except (TypeError, ValueError):
                    published = None
            if published is None:
                published = e.get("published") or e.get("updated") or None
            entries.append({
                "title": processor.clean_text(title),
                "link": link,
                "summary": summary,
                "published_at": published,
            })
        return entries
    except Exception as e:
        log.warning("feed 抓取失败 %s: %s", url, e)
        return None


def fetch_article_text(url, timeout=20):
    """trafilatura 提取正文，失败返回空字符串。"""
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return ""
        return trafilatura.extract(downloaded) or ""
    except Exception as e:
        log.warning("正文提取失败 %s: %s", url, e)
        return ""


def crawl_source(source, max_entries=30, fetch_content=True):
    """抓取单个信息源，返回处理好的 item dict 列表。"""
    entries = fetch_feed(source["url"])
    if entries is None:
        return None
    items = []
    for e in entries[:max_entries]:
        content = ""
        if fetch_content:
            content = fetch_article_text(e["link"])
        summary = processor.make_summary(content, e["summary"])
        if not summary:
            continue
        items.append({
            "title": e["title"],
            "summary": summary,
            "content": processor.clean_text(content)[:20000],
            "link": e["link"],
            "source": source["name"],
            "section": source["section"],
            "published_at": e["published_at"],
        })
    return items
