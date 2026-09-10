# -*- coding: utf-8 -*-
"""第二轮探测：为世界新闻/国内新闻板块寻找可用备选源。"""
import requests
import feedparser

CANDIDATES = [
    ("世界新闻", "联合早报国际(zaobao.com)", "https://www.zaobao.com/rss/realtime/world"),
    ("世界新闻", "联合早报国际(.sg)", "https://www.zaobao.com.sg/rss/realtime/world"),
    ("世界新闻", "中新网国际", "https://www.chinanews.com.cn/rss/world.xml"),
    ("世界新闻", "NHK 国际", "https://www3.nhk.or.jp/rss/news/cat6.xml"),
    ("世界新闻", "NPR News", "https://feeds.npr.org/1001/rss.xml"),
    ("世界新闻", "Sky News World", "https://feeds.skynews.com/feeds/rss/world.xml"),
    ("世界新闻", "France24 EN", "https://feeds.france24.com/en/rss"),
    ("世界新闻", "Moscow Times", "https://www.themoscowtimes.com/rss/news"),
    ("国内新闻", "联合早报中国(zaobao.com)", "https://www.zaobao.com/rss/realtime/china"),
    ("国内新闻", "FT中文网(https)", "https://www.ftchinese.com/rss/news"),
    ("国内新闻", "中新网滚动", "https://www.chinanews.com.cn/rss/scroll-news.xml"),
    ("国内新闻", "中新网国内", "https://www.chinanews.com.cn/rss/import.xml"),
    ("AI资讯", "雷锋网", "https://www.leiphone.com/feed"),
    ("AI资讯", "机器之心(备用路径)", "https://www.jiqizhixin.com/rss.xml"),
    ("AI资讯", "36氪", "https://36kr.com/feed"),
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
            return False, "parsed but 0 entries", 0
        return True, f"OK feed={feed.feed.get('title','')!r}", n
    except Exception as e:
        return False, f"{type(e).__name__}: {e}", 0

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    for section, name, url in CANDIDATES:
        ok, msg, n = probe(url)
        print(f"[{'PASS' if ok else 'FAIL'}] {section} | {name} | {url} | {msg} | n={n}", flush=True)
