# -*- coding: utf-8 -*-
"""Tavily 搜索封装。key 从 config.yaml 读取，不硬编码。"""
import logging

import requests

log = logging.getLogger("tavily")

API_URL = "https://api.tavily.com/search"


def tavily_search(api_key, query, max_results=10, timeout=30):
    """返回 [{title, url, content, published_at}]，失败返回 None。"""
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
        "include_answer": False,
    }
    try:
        r = requests.post(API_URL, json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return [{
            "title": item.get("title", "").strip(),
            "url": item.get("url", "").strip(),
            "content": item.get("content", ""),
            "published_at": item.get("published_date") or None,
        } for item in data.get("results", []) if item.get("url")]
    except Exception as e:
        log.warning("Tavily 搜索失败: %s", e)
        return None
