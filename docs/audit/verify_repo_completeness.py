# -*- coding: utf-8 -*-
"""仓库完整性检查：从 git 跟踪清单出发，验证「新克隆能否直接跑起来」。

用法： python docs/audit/verify_repo_completeness.py
"""
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def git(*args):
    r = subprocess.run(["git", *args], cwd=BASE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.stdout.strip(), r.returncode


tracked, _ = git("ls-files")
tracked = [x for x in tracked.splitlines() if x.strip()]
tracked_set = set(tracked)

# 运行时必需、但可能被 .gitignore 误伤的文件
REQUIRED = [
    "run.py",
    "update.py",
    "app/__init__.py",
    "app/api.py",
    "app/crawler.py",
    "app/db.py",
    "app/pipeline.py",
    "app/processor.py",
    "app/tavily_search.py",
    "app/worddict.py",
    "app/data/idioms.json",       # 习语词典：阅读模式高亮依赖它
    "static/index.html",
]

print("=" * 72)
print(f"Git 跟踪文件总数：{len(tracked)}")
print("=" * 72)
print()
print("运行时必需文件是否已入库：")
missing = []
for rel in REQUIRED:
    on_disk = os.path.isfile(os.path.join(BASE, rel))
    in_git = rel in tracked_set
    if in_git:
        flag = "OK  已入库"
    elif on_disk:
        flag = "缺失 磁盘有但未入库  ← 新克隆会缺"
        missing.append(rel)
    else:
        flag = "缺失 磁盘也没有"
        missing.append(rel)
    print(f"  {rel:<28} {flag}")

print()
if missing:
    print("被排除的原因：")
    for rel in missing:
        out, code = git("check-ignore", "-v", rel)
        print(f"  {rel}")
        print(f"    {out if out else '(未被 ignore 规则匹配，可能是从未 add)'}")
else:
    print("所有必需文件均已入库。")

print()
print("─" * 72)
print("影响评估")
print("─" * 72)
p = os.path.join(BASE, "app", "worddict.py")
if os.path.isfile(p):
    src = open(p, encoding="utf-8").read()
    if "idioms.json" in src and "except Exception" in src:
        print("  app/worddict.py 的 load_idioms() 在读取失败时 catch 异常并返回 []，")
        print("  → 文件缺失不会报错、不会崩溃，只会静默降级：习语高亮功能整体失效。")
        print("  这属于「静默失败」，普通冒烟测试发现不了。")
print()
sys.exit(1 if missing else 0)
