# -*- coding: utf-8 -*-
"""FastAPI 路由。"""
import logging
import threading
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from . import db, load_config, pipeline, processor, tavily_search as tv
from . import worddict

log = logging.getLogger("api")

# ---------- 公开访问限流（防滥用） ----------
# 规则: (路径前缀, 窗口秒数, 窗口内单 IP 最大次数)
RATE_RULES = [
    ("/api/search", 60, 10),      # 搜索：单 IP 10 次/分钟
    ("/api/search", 86400, 50),   # 搜索：单 IP 50 次/天
    ("/api/update", 1800, 1),     # 手动更新：单 IP 30 分钟 1 次
    ("/api/word", 60, 30),        # 点词解释：单 IP 30 次/分钟
]
SEARCH_DAILY_GLOBAL = 300  # 全站每日搜索总上限（保护 Tavily 配额）


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()
        self._search_day = {"date": "", "count": 0}

    async def dispatch(self, request, call_next):
        path = request.url.path
        # 经 Cloudflare Tunnel 时取真实访客 IP
        ip = request.headers.get("cf-connecting-ip") or (
            request.client.host if request.client else "unknown")
        now = time.time()
        limited = False
        with self._lock:
            for prefix, window, limit in RATE_RULES:
                if not path.startswith(prefix):
                    continue
                key = (ip, prefix, window)
                dq = self._hits[key]
                while dq and now - dq[0] > window:
                    dq.popleft()
                if len(dq) >= limit:
                    limited = True
                    break
                dq.append(now)
                if not dq:
                    self._hits.pop(key, None)
            if not limited and path.startswith("/api/search"):
                today = time.strftime("%Y-%m-%d")
                if self._search_day["date"] != today:
                    self._search_day.update(date=today, count=0)
                if self._search_day["count"] >= SEARCH_DAILY_GLOBAL:
                    limited = True
                else:
                    self._search_day["count"] += 1
        if limited:
            return JSONResponse(
                {"ok": False, "message": "请求过于频繁，请稍后再试"},
                status_code=429)
        return await call_next(request)


app = FastAPI(title="InfoRadar")
app.add_middleware(RateLimitMiddleware)

# 更新任务状态（内存态，供 /api/status 轮询）
_update_state = {
    "running": False,
    "progress": "",
    "last_error": "",
}
_update_lock = threading.Lock()


def _do_update():
    config = load_config()
    log_id = db.start_update_log()
    try:
        def cb(msg):
            _update_state["progress"] = msg
        new_count, errors = pipeline.run_update(config, progress_cb=cb)
        status = "success" if not errors else "partial"
        db.finish_update_log(log_id, status, new_count,
                             "; ".join(errors) if errors else "")
        _update_state["last_error"] = ""
    except Exception as e:
        log.exception("更新失败")
        db.finish_update_log(log_id, "failed", 0, str(e))
        _update_state["last_error"] = str(e)
    finally:
        with _update_lock:
            _update_state["running"] = False
            _update_state["progress"] = ""


@app.get("/")
def index():
    import os
    html = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "static", "index.html")
    return FileResponse(html)


@app.get("/api/sections")
def api_sections():
    config = load_config()
    # 保证所有配置板块都出现，即使暂时没有数据
    configured = []
    seen = set()
    for s in config.get("sources", []):
        if s.get("enabled", True) and s["section"] not in seen:
            seen.add(s["section"])
            configured.append(s["section"])
    counts = {r["section"]: r["count"] for r in db.get_sections()}
    return {"sections": [{"name": s, "count": counts.get(s, 0)} for s in configured]}


# 板块分组：父板块 → 子板块（父板块查询时聚合子板块内容）
SECTION_GROUPS = {
    "新闻": ["世界新闻", "国内新闻"],
    "学术": ["学术 · AI/CS", "学术 · 交互设计", "学术 · 心理学"],
}


@app.get("/api/items")
def api_items(section: str = Query(None), limit: int = Query(60, le=200)):
    if section in SECTION_GROUPS:
        # 子板块各自按时间排序后交叉混合，保证每个子板块都有露面机会
        subs = [db.get_items(section=sub, limit=limit)
                for sub in SECTION_GROUPS[section]]
        items = []
        for row in zip(*subs):
            items.extend(row)
        # 各子板块条数不均时，把剩余部分也接上
        longest = max((len(s) for s in subs), default=0)
        for i in range(len(items) // len(subs), longest):
            for s in subs:
                if i < len(s):
                    items.append(s[i])
        items = items[:limit]
    else:
        items = db.get_items(section=section, limit=limit)
    return {"items": items, "count": len(items)}


@app.post("/api/update")
def api_update():
    with _update_lock:
        if _update_state["running"]:
            return JSONResponse({"ok": False, "message": "更新正在进行中"},
                                status_code=409)
        _update_state["running"] = True
        _update_state["progress"] = "更新已启动"
    t = threading.Thread(target=_do_update, daemon=True)
    t.start()
    return {"ok": True, "message": "更新已在后台启动"}


@app.get("/api/status")
def api_status():
    config = load_config()
    logs = db.get_last_logs(5)
    counts = db.count_items()
    return {
        "running": _update_state["running"],
        "progress": _update_state["progress"],
        "last_error": _update_state["last_error"],
        "last_update": db.get_setting("last_update"),
        "last_update_new_count": db.get_setting("last_update_new_count", "0"),
        "schedule": config.get("schedule", {}),
        "item_counts": counts,
        "recent_logs": logs,
    }


@app.get("/api/search")
def api_search(q: str = Query(..., min_length=1)):
    config = load_config()
    api_key = (config.get("tavily") or {}).get("api_key", "")
    if not api_key:
        return JSONResponse({"ok": False, "message": "未配置 Tavily API key"},
                            status_code=500)
    max_results = int((config.get("tavily") or {}).get("max_results", 10))
    results = tv.tavily_search(api_key, q, max_results=max_results)
    if results is None:
        return JSONResponse({"ok": False, "message": "搜索请求失败"},
                            status_code=502)
    saved = []
    for r in results:
        pub = r["published_at"]
        if pub:
            pub = pub.replace("T", " ").replace("Z", "").strip()[:19]
        summary = processor.make_summary("", r["content"]) or r["content"][:300]
        db.insert_item(
            title=r["title"] or r["url"],
            summary=summary,
            content=r["content"],
            link=r["url"],
            source="Tavily 搜索",
            section="搜索结果",
            published_at=pub or None,
            is_search_result=1,
        )
        saved.append({
            "title": r["title"] or r["url"],
            "summary": summary,
            "link": r["url"],
            "source": "Tavily 搜索",
            "published_at": pub or None,
        })
    db.log_search(q, len(saved))
    return {"ok": True, "count": len(saved), "results": saved}


@app.get("/api/search/history")
def api_search_history():
    with db._lock, db._connect() as conn:
        rows = conn.execute(
            "SELECT keyword, searched_at, result_count FROM searches "
            "ORDER BY id DESC LIMIT 20").fetchall()
    return {"history": [dict(r) for r in rows]}


@app.get("/api/item/{item_id}")
def api_item(item_id: int):
    """单条详情（含 content 全文），供阅读模式使用。"""
    item = db.get_item(item_id)
    if not item:
        return JSONResponse({"ok": False, "message": "条目不存在"},
                            status_code=404)
    return {"ok": True, "item": item}


@app.get("/api/word")
def api_word(w: str = Query(..., min_length=1, max_length=50)):
    """英文点词解释：先查缓存，未命中走词典聚合（或 LLM 分支）。"""
    return worddict.lookup_word(w, config=load_config())


@app.get("/api/idioms")
def api_idioms():
    """内置习语/俚语/词组清单，供阅读模式高亮匹配。"""
    return {"idioms": worddict.load_idioms()}
