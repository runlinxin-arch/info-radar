# -*- coding: utf-8 -*-
"""一次性探测脚本：逐个请求候选 RSS 源，报告可用性与条目数。"""
import sys
import requests
import feedparser

CANDIDATES = [
    ("AI 资讯", "机器之心", "https://www.jiqizhixin.com/rss"),
    ("AI 资讯", "量子位", "https://www.qbitai.com/feed"),
    ("AI 资讯", "TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("世界新闻", "BBC World", "http://feeds.bbci.co.uk/news/world/rss.xml"),
    ("世界新闻", "The Guardian World", "https://www.theguardian.com/world/rss"),
    ("世界新闻", "Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("国内新闻", "BBC 中文", "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml"),
    ("国内新闻", "联合早报中国", "https://www.zaobao.com.sg/rss/realtime/china"),
    ("国内新闻", "FT中文网", "http://www.ftchinese.com/rss/news"),
    ("学术-AI/CS", "arXiv cs.AI (rss.arxiv.org)", "https://rss.arxiv.org/rss/cs.AI"),
    ("学术-AI/CS", "arXiv cs.CL (rss.arxiv.org)", "https://rss.arxiv.org/rss/cs.CL"),
    ("学术-AI/CS", "arXiv cs.CV (rss.arxiv.org)", "https://rss.arxiv.org/rss/cs.CV"),
    ("学术-AI/CS", "arXiv cs.AI (arxiv.org)", "https://arxiv.org/rss/cs.AI"),
    ("学术-交互设计", "arXiv cs.HC (rss.arxiv.org)", "https://rss.arxiv.org/rss/cs.HC"),
    ("学术-交互设计", "arXiv cs.HC (arxiv.org)", "https://arxiv.org/rss/cs.HC"),
    ("学术-心理学", "ScienceDaily Psychology", "https://www.sciencedaily.com/rss/mind_brain/psychology.xml"),
    ("学术-心理学", "PsyPost", "https://www.psypost.org/feed"),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) InfoRadar/1.0"}

def probe(url, timeout=20):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}", 0
        feed = feedparser.parse(r.content)
        n = len(feed.entries)
        if n == 0:
            return False, "解析成功但 0 条", 0
        title = feed.feed.get("title", "")
        return True, f"OK, feed标题={title!r}", n
    except Exception as e:
        return False, f"{type(e).__name__}: {e}", 0

def main():
    for section, name, url in CANDIDATES:
        ok, msg, n = probe(url)
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {section} | {name} | {url} | {msg} | 条目数={n}", flush=True)

if __name__ == "__main__":
    main()
