# -*- coding: utf-8 -*-
"""当前运行状态快照：数据库时间线、内容量、抓取健康度。

用法： python docs/audit/status_now.py
"""
import os
import sqlite3
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB = os.path.join(BASE, "data", "radar.db")

if not os.path.isfile(DB):
    raise SystemExit(f"找不到数据库：{DB}")

c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

print("=" * 70)
print(f"数据库：{DB}")
print(f"大小：{os.path.getsize(DB)/1024:.0f} KB  "
      f"完整性：{c.execute('PRAGMA integrity_check').fetchone()[0]}")
print("=" * 70)

print()
print("更新日志（最近 10 条）")
print(f"  {'id':>3} {'开始时间':<20} {'结束时间':<20} {'状态':<12} {'新增':>4}  消息")
for r in c.execute("SELECT id, started_at, finished_at, status, new_count, message "
                   "FROM update_logs ORDER BY id DESC LIMIT 10"):
    msg = (r["message"] or "")[:38]
    print(f"  {r['id']:>3} {str(r['started_at']):<20} {str(r['finished_at']):<20} "
          f"{str(r['status']):<12} {r['new_count']:>4}  {msg}")

print()
print("关键设置")
for k in ("last_update", "last_update_new_count"):
    row = c.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()
    print(f"  {k:<24} {row['value'] if row else '(未设置)'}")

last = c.execute("SELECT value FROM settings WHERE key='last_update'").fetchone()
if last and last["value"]:
    try:
        dt = datetime.strptime(last["value"], "%Y-%m-%d %H:%M:%S")
        hours = (datetime.now() - dt).total_seconds() / 3600
        print(f"  → 距上次成功更新：{hours:.1f} 小时（{hours/24:.1f} 天）")
    except ValueError:
        pass

print()
print("内容统计")
feed = c.execute("SELECT COUNT(*) FROM items WHERE is_search_result=0").fetchone()[0]
total = c.execute("SELECT COUNT(*) FROM items").fetchone()[0]
print(f"  资讯 {feed} 条 / 总计 {total} 条")
for r in c.execute("SELECT section, COUNT(*) n FROM items WHERE is_search_result=0 "
                   "GROUP BY section ORDER BY MIN(id)"):
    print(f"    {r['section']:<16} {r['n']:>3}")

print()
print("抓取健康度")
mx = c.execute("SELECT MAX(fetched_at) FROM items").fetchone()[0]
print(f"  最新条目抓取时间：{mx}")
n_content = c.execute("SELECT COUNT(*) FROM items WHERE LENGTH(content)>0").fetchone()[0]
print(f"  含正文的条目：{n_content}/{total}（fetch_full_content=false，预期很低）")
n_cache = c.execute("SELECT COUNT(*) FROM word_cache").fetchone()[0]
n_search = c.execute("SELECT COUNT(*) FROM searches").fetchone()[0]
print(f"  word_cache {n_cache} 条 / searches {n_search} 条（隐私路由仍在暴露）")

print()
print("信息源（按启用状态）")
for r in c.execute("SELECT name, section, enabled FROM sources ORDER BY enabled DESC, id"):
    print(f"  [{'启用' if r['enabled'] else '停用'}] {r['name']:<22} {r['section']}")
c.close()
