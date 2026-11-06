# -*- coding: utf-8 -*-
"""单元测试：/healthz 的新鲜度判定（纯函数，不依赖数据库与网络）。

用法： python docs/audit/test_healthz.py
退出码 0 = 全部通过
"""
import sys
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8")

# 让 `import app.api` 能找到项目根
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from app.api import compute_health, HEALTH_MAX_STALE_HOURS  # noqa: E402

NOW = datetime(2026, 11, 6, 12, 0, 0)


def fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


CASES = [
    # (说明, last_update, 期望 ok, 期望 reason)
    ("1 小时前（正常）",
     fmt(NOW - timedelta(hours=1)), True, "fresh"),
    ("4.5 小时前（正常上限附近）",
     fmt(NOW - timedelta(hours=4.5)), True, "fresh"),
    ("恰好 8 小时（边界，应为健康）",
     fmt(NOW - timedelta(hours=HEALTH_MAX_STALE_HOURS)), True, "fresh"),
    ("8.1 小时前（刚过阈值 → 陈旧）",
     fmt(NOW - timedelta(hours=8.1)), False, "stale"),
    ("3 天前（严重停更）",
     fmt(NOW - timedelta(days=3)), False, "stale"),
    ("从未更新过（None）", None, False, "no_update_record"),
    ("空字符串", "", False, "no_update_record"),
    ("时间串格式错误", "not-a-timestamp", False, "unparsable_timestamp"),
    ("日期不可能", "2026-13-45 99:99:99", False, "unparsable_timestamp"),
    ("未来时间（时钟回拨）",
     fmt(NOW + timedelta(hours=2)), True, "clock_skew"),
]

print("=" * 74)
print(f"/healthz 新鲜度判定测试（阈值 {HEALTH_MAX_STALE_HOURS} 小时，now={fmt(NOW)}）")
print("=" * 74)

failed = 0
for desc, last, want_ok, want_reason in CASES:
    got = compute_health(last, now=NOW)
    ok = (got["ok"] == want_ok and got["reason"] == want_reason)
    if not ok:
        failed += 1
    mark = "通过" if ok else "失败"
    print(f"  [{mark}] {desc:<28} ok={got['ok']!s:<5} reason={got['reason']:<20} "
          f"hours_since={got['hours_since']}")

# 自定义阈值
got = compute_health(fmt(NOW - timedelta(hours=3)), now=NOW, max_stale_hours=2)
ok = got["ok"] is False and got["reason"] == "stale"
if not ok:
    failed += 1
print(f"  [{'通过' if ok else '失败'}] {'自定义阈值 2h，数据 3h 前':<28} "
      f"ok={got['ok']!s:<5} reason={got['reason']}")

# 返回值字段完整性
got = compute_health(fmt(NOW - timedelta(hours=1)), now=NOW)
need = {"ok", "reason", "last_update", "hours_since", "max_stale_hours"}
missing = need - set(got)
if missing:
    failed += 1
    print(f"  [失败] 返回字段缺失: {missing}")
else:
    print(f"  [通过] 返回字段完整: {sorted(need)}")

print()
print(f"合计 {len(CASES) + 2} 项，失败 {failed} 项。")

# ---------------------------------------------------------------------------
# 路由级集成测试：证明 /healthz 真的会返回 503（纯函数对 ≠ 路由接对了）
# 用 mock 替换 db.get_setting，不改动生产数据库。
# ---------------------------------------------------------------------------
print()
print("=" * 74)
print("路由级测试（mock 数据库，不触碰真实数据）")
print("=" * 74)

try:
    from unittest import mock
    from fastapi.testclient import TestClient
    from app import api
    client = TestClient(api.app)
    route_failed = 0

    def check_route(desc, patcher, want_status, want_ok, want_reason=None):
        global route_failed
        with patcher:
            r = client.get("/healthz")
        body = r.json()
        ok = r.status_code == want_status and body.get("ok") is want_ok
        if want_reason:
            ok = ok and body.get("reason") == want_reason
        if not ok:
            route_failed += 1
        print(f"  [{'通过' if ok else '失败'}] {desc:<26} "
              f"HTTP {r.status_code}  ok={body.get('ok')}  reason={body.get('reason')}")
        return ok

    fresh_ts = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    stale_ts = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")

    check_route("数据 1 小时前 -> 200", mock.patch.object(
        api.db, "get_setting", return_value=fresh_ts), 200, True, "fresh")
    check_route("数据 3 天前 -> 503", mock.patch.object(
        api.db, "get_setting", return_value=stale_ts), 503, False, "stale")
    # db 异常这条会把堆栈写进日志，测试里顺手静音，避免污染输出
    with mock.patch.object(api.log, "exception"):
        check_route("数据库抛异常 -> 503", mock.patch.object(
            api.db, "get_setting", side_effect=RuntimeError("db down")),
            503, False, "db_error")
    check_route("无更新记录 -> 503", mock.patch.object(
        api.db, "get_setting", return_value=None), 503, False, "no_update_record")

    # 真实数据不被动：撤销 mock 后再打一次，应回到 200
    r = client.get("/healthz")
    ok = r.status_code == 200
    if not ok:
        route_failed += 1
    print(f"  [{'通过' if ok else '失败'}] {'撤销 mock，读真实数据库':<26} "
          f"HTTP {r.status_code}  hours_since={r.json().get('hours_since')}")

    print()
    print(f"路由级 {5} 项，失败 {route_failed} 项。")
    failed += route_failed
except ImportError as e:
    print(f"  [跳过] 缺少 httpx/TestClient：{e}")

print()
print("总结果：", "全部通过" if failed == 0 else f"失败 {failed} 项")
sys.exit(1 if failed else 0)
