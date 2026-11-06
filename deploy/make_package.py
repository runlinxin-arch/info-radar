#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""打包 InfoRadar 迁移包（在本机 Windows 上运行）。

做四件事：
  1. 用 SQLite 在线备份 API 导出 data/radar.db -> deploy/_package/data/radar.db
     （WAL 模式下直接拷文件会丢 -wal 里的未合并事务，必须走 .backup）
  2. 复制 config.yaml（含 Tavily key）到包里
  3. 按白名单收集代码/静态资源/文档
  4. 打成 deploy/inforadar-migrate-<时间戳>.tar.gz，并打印清单

用法：  python deploy/make_package.py
"""
from __future__ import annotations

import gzip
import os
import shutil
import sqlite3
import sys
import tarfile
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPLOY_DIR = os.path.join(BASE_DIR, "deploy")
PKG_DIR = os.path.join(DEPLOY_DIR, "_package")
DB_PATH = os.path.join(BASE_DIR, "data", "radar.db")

# 要打进包里的文件和目录（相对项目根）
INCLUDE_DIRS = ["app", "static", "docs", "deploy"]
INCLUDE_FILES = ["run.py", "update.py", "config.yaml"]
# deploy/ 里不需要进包的东西（含本地 SSH 公钥残留文件、打包产物）
DEPLOY_EXCLUDE = {"_package", "__pycache__"}
DEPLOY_EXCLUDE_FILES = {"id_ed25519.pub", "id_ed25519_pub.txt"}


def log(msg: str) -> None:
    print(f"[打包] {msg}", flush=True)


def backup_sqlite() -> str:
    """用 sqlite3 在线备份 API 导出一致性快照，返回产物路径。"""
    if not os.path.isfile(DB_PATH):
        raise SystemExit(f"找不到数据库：{DB_PATH}")
    dest_dir = os.path.join(PKG_DIR, "data")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, "radar.db")

    src = sqlite3.connect(DB_PATH, timeout=30)
    try:
        if os.path.exists(dest):
            os.remove(dest)
        dst = sqlite3.connect(dest)
        try:
            with dst:
                src.backup(dst)          # 原子、含 WAL 中已提交的事务
            dst.execute("PRAGMA journal_mode=DELETE")  # 包里不留 -wal/-shm
            dst.execute("VACUUM")
        finally:
            dst.close()
        # 自检
        check = sqlite3.connect(dest)
        try:
            ok = check.execute("PRAGMA integrity_check").fetchone()[0]
            items = check.execute(
                "SELECT COUNT(*) FROM items WHERE is_search_result=0").fetchone()[0]
            sections = check.execute(
                "SELECT COUNT(DISTINCT section) FROM items "
                "WHERE is_search_result=0").fetchone()[0]
            search_items = check.execute(
                "SELECT COUNT(*) FROM items WHERE is_search_result=1").fetchone()[0]
            last = check.execute(
                "SELECT value FROM settings WHERE key='last_update'").fetchone()
        finally:
            check.close()
    finally:
        src.close()

    if ok != "ok":
        raise SystemExit(f"备份出的数据库自检失败：{ok}")
    size = os.path.getsize(dest)
    log(f"数据库已备份：资讯 {items} 条 / {sections} 个板块 / "
        f"搜索结果 {search_items} 条 / last_update={last[0] if last else 'N/A'} / "
        f"{size/1024:.0f} KB")
    return dest


def collect_files() -> list[tuple[str, str]]:
    """返回 [(绝对路径, 归档内相对路径)]。"""
    pairs: list[tuple[str, str]] = []

    for name in INCLUDE_FILES:
        p = os.path.join(BASE_DIR, name)
        if os.path.isfile(p):
            pairs.append((p, name))
        else:
            log(f"警告：缺少 {name}")

    for d in INCLUDE_DIRS:
        root = os.path.join(BASE_DIR, d)
        if not os.path.isdir(root):
            log(f"警告：缺少目录 {d}")
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            # 就地过滤，避免走进 __pycache__ / _package
            dirnames[:] = [
                x for x in dirnames
                if x != "__pycache__"
                and not (d == "deploy" and x in DEPLOY_EXCLUDE)
            ]
            for fn in filenames:
                if fn.endswith((".pyc", ".pyo")):
                    continue
                if d == "deploy" and fn.endswith(".tar.gz"):
                    continue
                if d == "deploy" and fn in DEPLOY_EXCLUDE_FILES:
                    continue
                abspath = os.path.join(dirpath, fn)
                rel = os.path.relpath(abspath, BASE_DIR).replace("\\", "/")
                pairs.append((abspath, rel))

    # 追加备份好的数据库
    db_dest = os.path.join(PKG_DIR, "data", "radar.db")
    if os.path.isfile(db_dest):
        pairs.append((db_dest, "data/radar.db"))
    return pairs


def make_tarball(pairs: list[tuple[str, str]]) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = os.path.join(DEPLOY_DIR, f"inforadar-migrate-{stamp}.tar.gz")
    # mtime 固定，保证可复现
    with tarfile.open(out, "w:gz", compresslevel=9) as tar:
        for abspath, rel in sorted(pairs, key=lambda x: x[1]):
            info = tar.gettarinfo(abspath, arcname=rel)
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            # .sh 保留可执行位，其余 0644
            info.mode = 0o755 if rel.endswith(".sh") else 0o644
            with open(abspath, "rb") as fh:
                tar.addfile(info, fh)
    return out


def main() -> int:
    log(f"项目根目录：{BASE_DIR}")
    if os.path.isdir(PKG_DIR):
        shutil.rmtree(PKG_DIR)
    os.makedirs(PKG_DIR, exist_ok=True)

    backup_sqlite()
    pairs = collect_files()
    if not any(rel == "config.yaml" for _, rel in pairs):
        log("警告：config.yaml 没进包，服务器上必须手动放一份")

    out = make_tarball(pairs)
    size = os.path.getsize(out)

    print()
    log(f"共 {len(pairs)} 个文件，产物：{out}")
    log(f"大小：{size/1024:.1f} KB")
    print()
    print("包内清单：")
    for _, rel in sorted(pairs, key=lambda x: x[1]):
        print(f"  {rel}")
    print()
    print("下一步（在项目目录下用 Git Bash 或 PowerShell 执行）：")
    print(f"  scp \"{out}\" root@<服务器IP>:/root/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
