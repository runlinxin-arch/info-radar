# -*- coding: utf-8 -*-
"""FastAPI 路由。"""
import logging
import os
import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from . import crawler, db, feeds, load_config, pipeline, processor, tavily_search as tv
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
# 全站每日搜索总上限（保护 Tavily 配额）。
# Tavily 账号是 Researcher 计划：1000 次/月 ÷ 30 天 ≈ 33 次/天，取 30 留余量。
# 原先写 300（× 30 天 = 9000）会让一个月额度在 3.3 天内打光。
SEARCH_DAILY_GLOBAL = 30

# 所有限流窗口里最长的那个（秒），用于判断某个 IP 的记录是否还可能有影响
MAX_WINDOW = max(window for _, window, _ in RATE_RULES)


class RateLimitMiddleware(BaseHTTPMiddleware):
    # 清理 _hits 的最小间隔（秒）。只影响内存回收，不参与限流判定。
    SWEEP_INTERVAL = 60

    def __init__(self, app):
        super().__init__(app)
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()
        self._search_day = {"date": "", "count": 0}
        self._last_sweep = 0.0

    def _sweep(self, now):
        """回收 _hits 里已经不可能再影响判定的 key。

        defaultdict 不会自行删除 key：某个 IP 不再来访时，它的 deque 会一直留着。
        只有「最后一条记录也已经滑出最长窗口」的 key 才可以安全删除——
        这样无论限流规则怎么调，都不会因为清理而放过本该拦住的请求。
        """
        stale = [key for key, dq in list(self._hits.items())
                 if not dq or now - dq[-1] > MAX_WINDOW]
        for key in stale:
            del self._hits[key]

    async def dispatch(self, request, call_next):
        path = request.url.path
        # 经 Cloudflare Tunnel 时取真实访客 IP
        ip = request.headers.get("cf-connecting-ip") or (
            request.client.host if request.client else "unknown")
        now = time.time()
        limited = False
        with self._lock:
            if now - self._last_sweep >= self.SWEEP_INTERVAL:
                self._sweep(now)
                self._last_sweep = now
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


# ---------- robots.txt / sitemap.xml / RSS ----------
# 三者都是站点级入口，不属于 /api/ 命名空间，也不参与限流。
# Cloudflare 开启 Bot Preference Sync 时，会把它的 Managed content **前置拼接**
# 在本站 robots.txt 之前（只有 origin 返回 200 才会合并），所以这里只写站点自身规则。
_STATIC_CACHE = {"Cache-Control": "public, max-age=600"}


@app.get("/robots.txt", include_in_schema=False)
def robots_txt():
    return Response(feeds.render_robots(),
                    media_type="text/plain; charset=utf-8",
                    headers=_STATIC_CACHE)


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml():
    body = feeds.render_sitemap(db.get_setting("last_update"))
    return Response(body,
                    media_type="application/xml; charset=utf-8",
                    headers=_STATIC_CACHE)


@app.get("/feed.xml", include_in_schema=False)
def feed_xml():
    items = db.get_items(limit=feeds.FEED_LIMIT)
    body = feeds.render_rss(items, db.get_setting("last_update"))
    return Response(body,
                    media_type="application/rss+xml; charset=utf-8",
                    headers=_STATIC_CACHE)


# IndexNow 所有权校验文件。
# IndexNow 是 Bing / Yandex / Seznam 等共用的「免登录提交」协议：
# 站点在根路径放一个 <key>.txt，内容就是这个 key，即可直接推送 URL。
# 注意：key 本身是**公开信息**（就是用来证明你控制该站点的），不是密钥。
INDEXNOW_KEY = "6c1251d53cc84103413cf3db781d93f0"


@app.get(f"/{INDEXNOW_KEY}.txt", include_in_schema=False)
def indexnow_key_file():
    return Response(INDEXNOW_KEY,
                    media_type="text/plain; charset=utf-8",
                    headers=_STATIC_CACHE)


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


# ---------- 外部监控探针（UptimeRobot 等） ----------
# config.yaml 的刷新策略是「>4 小时就更新」，检查间隔 30 分钟，
# 因此健康状态下两次成功更新的最大间隔约 4~4.5 小时。留一倍余量取 8 小时。
HEALTH_MAX_STALE_HOURS = 8


def compute_health(last_update, now=None, max_stale_hours=HEALTH_MAX_STALE_HOURS):
    """把 last_update 时间串换算成健康结论。

    抽成纯函数是为了能脱离数据库单测（见 docs/audit/test_healthz.py）。
    """
    now = now or datetime.now()
    base = {"last_update": last_update, "max_stale_hours": max_stale_hours,
            "hours_since": None}

    if not last_update:
        return {**base, "ok": False, "reason": "no_update_record"}

    try:
        dt = datetime.strptime(str(last_update), "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return {**base, "ok": False, "reason": "unparsable_timestamp"}

    hours = (now - dt).total_seconds() / 3600
    base["hours_since"] = round(hours, 1)

    # 时间在未来：通常是时钟回拨，按健康处理，避免误报把监控变成噪音源
    if hours < 0:
        return {**base, "ok": True, "reason": "clock_skew"}

    stale = hours > max_stale_hours
    return {**base, "ok": not stale, "reason": "stale" if stale else "fresh"}


@app.api_route("/healthz", methods=["GET", "HEAD"])
def healthz():
    """外部监控专用：同时检查「进程活着」和「内容新鲜」。

    200 -> 应用在跑，且最近一次成功更新在阈值内
    503 -> 应用在跑但内容已陈旧（抓取循环失效 / 信息源全部被挡）

    站点整体不可达时监控端拿不到任何响应，同样会告警——所以一个 monitor
    就同时覆盖了「挂了」和「静默停更」两种故障。
    """
    try:
        last = db.get_setting("last_update")
    except Exception:
        log.exception("healthz 读取数据库失败")
        return JSONResponse(
            {"ok": False, "reason": "db_error", "last_update": None,
             "hours_since": None, "max_stale_hours": HEALTH_MAX_STALE_HOURS},
            status_code=503)

    health = compute_health(last)
    return JSONResponse(health, status_code=200 if health["ok"] else 503)


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
        # 第三方搜索结果的 url 同样不可信，落库前统一过协议白名单
        link = crawler.safe_link(r.get("url"))
        if not link:
            log.warning("搜索结果链接协议不被允许，已跳过: %r", r.get("url"))
            continue
        pub = r["published_at"]
        if pub:
            pub = pub.replace("T", " ").replace("Z", "").strip()[:19]
        summary = processor.make_summary("", r["content"]) or r["content"][:300]
        db.insert_item(
            title=r["title"] or link,
            summary=summary,
            content=r["content"],
            link=link,
            source="Tavily 搜索",
            section="搜索结果",
            published_at=pub or None,
            is_search_result=1,
        )
        saved.append({
            "title": r["title"] or link,
            "summary": summary,
            "link": link,
            "source": "Tavily 搜索",
            "published_at": pub or None,
        })
    db.log_search(q, len(saved))
    return {"ok": True, "count": len(saved), "results": saved}


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


# ---------- 站点根校验文件（Google Search Console / Bing / Yandex） ----------
# GSC 的「HTML 文件」验证方式要求 https://<域名>/google<token>.html 原样返回该文件。
# 把文件放进 static/verify/ 即生效，不需要改代码。
#
# ⚠️ 这个路由必须注册在**最末尾**：它匹配任意单段路径，
#    若放在前面会把 /robots.txt、/feed.xml 之类的字面路由抢掉。
_VERIFY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "verify")
_VERIFY_NAME = re.compile(
    r"^(?:google[0-9A-Za-z]+\.html|BingSiteAuth\.xml|yandex_[0-9A-Za-z]+\.html)$")


@app.get("/{filename}", include_in_schema=False)
def root_verify_file(filename: str):
    """只放行搜索引擎校验文件的固定文件名，其余一律 404。"""
    if not _VERIFY_NAME.match(filename):
        raise HTTPException(status_code=404, detail="Not Found")
    path = os.path.join(_VERIFY_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Not Found")
    media = "application/xml" if filename.endswith(".xml") else "text/html"
    return FileResponse(path, media_type=media,
                        headers={"Cache-Control": "public, max-age=600"})
