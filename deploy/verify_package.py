# -*- coding: utf-8 -*-
"""校验迁移包内容（打包后跑一次，确认没漏文件、没混进密钥、数据库自检通过）。

用法：python deploy/verify_package.py
"""
import glob
import os
import sqlite3
import sys
import tarfile

sys.stdout.reconfigure(encoding="utf-8")

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tbs = sorted(glob.glob(os.path.join(base, "deploy", "inforadar-migrate-*.tar.gz")),
             key=os.path.getmtime)
assert tbs, "没找到迁移包"
tb = tbs[-1]
print("包：", os.path.basename(tb), f"({os.path.getsize(tb)/1024:.1f} KB)")

need = ["run.py", "update.py", "config.yaml", "data/radar.db",
        "app/__init__.py", "app/api.py", "app/crawler.py", "app/db.py",
        "app/pipeline.py", "app/processor.py", "app/tavily_search.py",
        "app/worddict.py", "app/data/idioms.json", "static/index.html",
        "deploy/install.sh", "deploy/deploy.sh", "deploy/backup.sh",
        "deploy/requirements.txt", "deploy/cloudflared/config.yml",
        "deploy/systemd/inforadar.service",
        "deploy/systemd/cloudflared-inforadar.service"]

with tarfile.open(tb) as t:
    names = t.getnames()
    print("条目数：", len(names))

    leaked = [n for n in names if n.endswith("id_ed25519.pub")
              or n.endswith("id_ed25519_pub.txt")]
    assert not leaked, f"公钥残留混进包：{leaked}"
    print("[OK] 无多余公钥残留")

    missing = [n for n in need if n not in names]
    assert not missing, f"缺少文件：{missing}"
    print(f"[OK] {len(need)} 个必需文件全部在包内")

    for n in [x for x in names if x.endswith(".sh")]:
        mode = t.getmember(n).mode
        assert mode & 0o111, f"{n} 丢了可执行位（{oct(mode)}）"
    print("[OK] 所有 .sh 保留可执行位")

    d = os.path.join(base, "deploy", "_verify_tmp")
    os.makedirs(d, exist_ok=True)
    t.extract("data/radar.db", d, filter="data")
    db = os.path.join(d, "data", "radar.db")
    c = sqlite3.connect(db)
    integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
    total = c.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    feeds = c.execute(
        "SELECT COUNT(*) FROM items WHERE is_search_result=0").fetchone()[0]
    secs = c.execute(
        "SELECT COUNT(DISTINCT section) FROM items WHERE is_search_result=0"
    ).fetchone()[0]
    per = c.execute(
        "SELECT section, COUNT(*) FROM items WHERE is_search_result=0 "
        "GROUP BY section").fetchall()
    last = c.execute(
        "SELECT value FROM settings WHERE key='last_update'").fetchone()
    wc = c.execute("SELECT COUNT(*) FROM word_cache").fetchone()[0]
    c.close()

    assert integrity == "ok", integrity
    print(f"[OK] 数据库完整性：{integrity}")
    print(f"     总条目 {total}（资讯 {feeds} + 搜索 {total - feeds}）")
    print(f"     板块 {secs} 个，分布：{[(s, n) for s, n in per]}")
    print(f"     单词缓存 {wc} 条，last_update = {last[0] if last else None}")
    assert feeds == 180, f"资讯条数应为 180，实际 {feeds}"

print("\n全部校验通过。")
