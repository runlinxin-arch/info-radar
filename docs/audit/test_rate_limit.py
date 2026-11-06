# -*- coding: utf-8 -*-
"""回归测试：限流额度、死代码清理、_sweep 回收。

对应任务 C 的第 2 条改动。关键约束：只允许删除死代码并新增定期清理，
**限流判定语义不得改变**。因此除了静态断言，还直接驱动中间件跑一遍
「30 次放行 / 第 31 次 429 / 窗口滑过后恢复」，证明语义没变。

不联网、不写数据库：用构造出来的 Request + 桩 call_next，
不经过任何真实路由（/api/word 会真去查词典）。

用法： python docs/audit/test_rate_limit.py
退出码 0 = 全部通过
"""
import asyncio
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

from starlette.requests import Request  # noqa: E402

from app import api  # noqa: E402
from app.api import (  # noqa: E402
    MAX_WINDOW,
    RATE_RULES,
    SEARCH_DAILY_GLOBAL,
    RateLimitMiddleware,
)

failed = 0
total = 0


def report(desc, ok, extra=""):
    global failed, total
    total += 1
    if not ok:
        failed += 1
    print(f"  [{'通过' if ok else '失败'}] {desc}{extra}")


# ---------------------------------------------------------------- 静态断言
print("=" * 76)
print("限流热修测试")
print("=" * 76)
print("静态断言：")

report(f"SEARCH_DAILY_GLOBAL = {SEARCH_DAILY_GLOBAL} <= 33"
       f"（1000 次/月 ÷ 30 天 ≈ 33）", SEARCH_DAILY_GLOBAL <= 33)
report(f"月度推算 {SEARCH_DAILY_GLOBAL * 30} <= 1000 次",
       SEARCH_DAILY_GLOBAL * 30 <= 1000)
expected_max = max(w for _, w, _ in RATE_RULES)
report(f"MAX_WINDOW = {MAX_WINDOW} 等于最长窗口 {expected_max}",
       MAX_WINDOW == expected_max)

src = open(os.path.join(BASE, "app", "api.py"), encoding="utf-8").read()
report("死代码分支已删除（append 之后不再有 if not dq）",
       not re.search(r"dq\.append\(now\)\s*\n\s*if not dq:", src))
report("已无 self._hits.pop 旧清理写法", "_hits.pop" not in src)
report("定义了 _sweep()", bool(re.search(r"def _sweep\(self,\s*now\)", src)))
report("dispatch 内每 SWEEP_INTERVAL 最多 sweep 一次",
       bool(re.search(r"now - self\._last_sweep >= self\.SWEEP_INTERVAL", src)))
report(f"SWEEP_INTERVAL = {getattr(RateLimitMiddleware, 'SWEEP_INTERVAL', None)} 秒",
       getattr(RateLimitMiddleware, "SWEEP_INTERVAL", None) == 60)

# 现有语义必须保持原样
report("_search_day 日计数逻辑未被改动",
       bool(re.search(r'if self\._search_day\["date"\] != today:', src)))
report("cf-connecting-ip 取值逻辑未被改动",
       'request.headers.get("cf-connecting-ip")' in src)
report("limited 判定仍先 break 再走全站日限",
       bool(re.search(r"if len\(dq\) >= limit:\s*\n\s*limited = True\s*\n\s*break", src)))


# ---------------------------------------------------------------- 行为断言
def make_request(path, ip="203.0.113.9"):
    scope = {
        "type": "http", "http_version": "1.1", "method": "GET",
        "scheme": "http", "path": path, "raw_path": path.encode(),
        "query_string": b"", "root_path": "",
        "headers": [(b"cf-connecting-ip", ip.encode())],
        "client": ("127.0.0.1", 40000), "server": ("testserver", 80),
    }
    return Request(scope)


async def _ok(request):
    from starlette.responses import JSONResponse
    return JSONResponse({"ok": True})


def call(mw, path, ip="203.0.113.9"):
    resp = asyncio.run(mw.dispatch(make_request(path, ip), _ok))
    return resp.status_code


print()
print(f"行为断言（直接驱动中间件，/api/word 规则 = "
      f"{[r for r in RATE_RULES if r[0] == '/api/word']}）：")

mw = RateLimitMiddleware(app=lambda *a, **k: None)

# 该规则是 (60s, 30 次)：前 30 次放行，第 31 次 429
codes = [call(mw, "/api/word") for _ in range(30)]
report(f"前 30 次全部放行（实际 {sum(1 for c in codes if c == 200)} 次 200）",
       all(c == 200 for c in codes))
code31 = call(mw, "/api/word")
report(f"第 31 次返回 429（实际 {code31}）", code31 == 429)

# 不同 IP 互不影响
report("换一个 IP 仍可放行（未被串号）", call(mw, "/api/word", ip="198.51.100.7") == 200)

# 窗口滑过 60 秒后恢复
real_time = api.time.time
try:
    api.time.time = lambda: real_time() + 61
    code_after = call(mw, "/api/word")
finally:
    api.time.time = real_time
report(f"窗口滑过 60 秒后恢复放行（实际 {code_after}）", code_after == 200)

# 不受限路径不产生记录
before = len(mw._hits)
for _ in range(5):
    call(mw, "/api/idioms")
report("不受限路径不写入 _hits", len(mw._hits) == before)

# ---------------------------------------------------------------- _sweep
print()
print("_sweep 回收断言：")
mw2 = RateLimitMiddleware(app=lambda *a, **k: None)
now = 1_000_000.0
k_expired = ("1.1.1.1", "/api/search", 60)
k_fresh = ("2.2.2.2", "/api/search", 60)
k_empty = ("3.3.3.3", "/api/search", 60)

mw2._hits[k_expired].extend([now - MAX_WINDOW - 1])   # 最后一条也已滑出最长窗口
mw2._hits[k_fresh].extend([now - 5])                  # 刚刚访问过
_ = mw2._hits[k_empty]                                # 空 deque（defaultdict 残留）
report("构造完成：1 个过期 / 1 个新鲜 / 1 个空", len(mw2._hits) == 3)

mw2._sweep(now)
report("过期 key 被回收", k_expired not in mw2._hits)
report("新鲜 key 被保留", k_fresh in mw2._hits)
report("空 deque 被回收", k_empty not in mw2._hits)
report("回收后仅剩 1 个 key", len(mw2._hits) == 1)

print()
print(f"合计 {total} 项，失败 {failed} 项。")
sys.exit(1 if failed else 0)
