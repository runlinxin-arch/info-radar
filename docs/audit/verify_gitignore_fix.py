# -*- coding: utf-8 -*-
"""在临时仓库里验证 .gitignore 规则语义，不触碰真实仓库。

对比：
  data/   （未锚定） → 会误伤 app/data/
  /data/  （锚定）   → 只命中仓库根的 data/

用法： python docs/audit/verify_gitignore_fix.py
"""
import os
import shutil
import stat
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

SCRATCH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "deploy", "_scratch_gitignore_test")


def force_rmtree(path):
    """Windows 上 .git/objects 是只读的，rmtree 需要先去掉只读位。"""
    def on_error(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass
    shutil.rmtree(path, onerror=on_error)


def run(*args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def trial(rule: str) -> dict:
    if os.path.isdir(SCRATCH):
        force_rmtree(SCRATCH)
    os.makedirs(SCRATCH, exist_ok=True)

    # 复刻真实结构
    os.makedirs(os.path.join(SCRATCH, "app", "data"))
    os.makedirs(os.path.join(SCRATCH, "data"))
    for rel in ("app/data/idioms.json",
                "app/api.py",
                "data/radar.db",
                "run.py"):
        p = os.path.join(SCRATCH, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("x")

    with open(os.path.join(SCRATCH, ".gitignore"), "w", encoding="utf-8") as f:
        f.write(f"# runtime db\n{rule}\n*.db\n*.db-shm\n*.db-wal\n")

    run("git", "init", "-q", cwd=SCRATCH)
    run("git", "add", "-A", cwd=SCRATCH)
    out = run("git", "ls-files", cwd=SCRATCH).stdout
    tracked = set(out.splitlines())

    result = {}
    for rel in ("app/data/idioms.json", "data/radar.db", "app/api.py", "run.py"):
        result[rel] = rel in tracked
    force_rmtree(SCRATCH)
    return result


print("=" * 76)
print("验证：.gitignore 里 data/ 与 /data/ 的语义差异（临时仓库，已自动清理）")
print("=" * 76)

cases = {"data/（当前写法）": "data/", "/data/（修复写法）": "/data/"}
for label, rule in cases.items():
    r = trial(rule)
    print(f"\n规则 {label}")
    for rel, tracked in r.items():
        mark = "入库" if tracked else "被忽略"
        print(f"  {rel:<26} {mark}")
    # 判定
    ok_idioms = r["app/data/idioms.json"]
    ok_db = not r["data/radar.db"]
    ok_code = r["app/api.py"] and r["run.py"]
    verdict = "通过" if (ok_idioms and ok_db and ok_code) else "不通过"
    print(f"  → 期望：词典入库 / 数据库忽略 / 代码入库   实际：{verdict}")

print()
print("=" * 76)
print("结论：把第 12 行 `data/` 改为 `/data/` 即可，其余忽略规则不受影响。")
print("=" * 76)
