# -*- coding: utf-8 -*-
"""收尾验收：证明「一个全新克隆出来的仓库」功能是完整的。

做三件事：
  1. 用 `git archive HEAD` 导出一份"只有已提交内容"的干净副本（等价于新克隆的工作区）
  2. 在副本里真正 import 应用并加载习语词典 —— 证明不是"文件在，但加载不出来"
  3. 反向核对：迁移包里需要的东西，是否都已在 git 里（排除有意的运行时文件）

用法： python docs/audit/verify_clone_works.py
退出码 0 = 全新克隆可用
"""
import os
import shutil
import subprocess
import sys
import tarfile

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORK = os.path.join(BASE, "deploy", "_clone_verify")
TAR = os.path.join(BASE, "deploy", "_clone_verify.tar")

# 有意不入库的运行时文件：迁移包里有，但 git 里不该有
INTENTIONAL_UNTRACKED = {"config.yaml", "data/radar.db"}


def force_rm(path):
    if not os.path.exists(path):
        return
    if os.path.isfile(path):
        os.chmod(path, 0o666)
        os.remove(path)
        return
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            try:
                os.chmod(os.path.join(dirpath, f), 0o666)
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)


def git(*args):
    # -c core.quotePath=false：否则中文文件名会被转义成 "\347\224\237..."，
    # 与 tar 里的原始名字对不上，产生假阳性
    r = subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=BASE,
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.stdout, r.returncode


print("=" * 74)
print("全新克隆可用性验收")
print("=" * 74)

force_rm(WORK)
force_rm(TAR)

# ---- 1. 导出只有已提交内容的副本 -------------------------------------------
_, code = git("archive", "-o", TAR, "HEAD")
if code != 0:
    print("  [失败] git archive 执行失败")
    sys.exit(1)
os.makedirs(WORK, exist_ok=True)
with tarfile.open(TAR) as t:
    t.extractall(WORK)
force_rm(TAR)

files = []
for dirpath, _, filenames in os.walk(WORK):
    for f in filenames:
        files.append(os.path.relpath(os.path.join(dirpath, f), WORK).replace("\\", "/"))
files.sort()
print(f"  导出 {len(files)} 个文件（等价于新克隆的工作区）")

# ---- 2. 关键文件 + 真正能加载 ----------------------------------------------
critical = ["run.py", "app/worddict.py", "app/data/idioms.json", "static/index.html"]
ok = True
for rel in critical:
    exists = os.path.isfile(os.path.join(WORK, rel))
    size = os.path.getsize(os.path.join(WORK, rel)) if exists else 0
    print(f"  {'OK ' if exists else '缺失'} {rel:<26} {size} 字节")
    ok = ok and exists

# 真正 import 一次，确认词典能加载（防止"文件在但路径错/内容坏"）
sys.path.insert(0, WORK)
try:
    from app import worddict  # noqa: E402
except Exception as e:  # pragma: no cover
    print(f"  [失败] 从克隆副本 import app.worddict 失败：{e}")
    force_rm(WORK)
    sys.exit(1)

# 必须确认导入的是副本里的模块，而不是本仓库的
loaded_from = os.path.abspath(worddict.__file__)
if not loaded_from.startswith(os.path.abspath(WORK)):
    print(f"  [失败] 导入的不是副本里的模块：{loaded_from}")
    force_rm(WORK)
    sys.exit(1)

idioms = worddict.load_idioms()
print(f"  OK  load_idioms() 从副本加载到 {len(idioms)} 条习语")
if not idioms:
    print("  [失败] 词典为空 —— 这正是 idioms.json 缺失时的静默降级表现")
    ok = False

# ---- 3. 反向核对：迁移包里该有的，git 里是否都有 ---------------------------
print()
print("  反向核对迁移包 vs git：")
pkgs = sorted(
    [os.path.join(BASE, "deploy", f) for f in os.listdir(os.path.join(BASE, "deploy"))
     if f.startswith("inforadar-migrate-") and f.endswith(".tar.gz")],
    key=os.path.getmtime)
tracked = set(x for x in git("ls-files")[0].splitlines() if x.strip())

if not pkgs:
    print("    (没有迁移包，跳过)")
else:
    with tarfile.open(pkgs[-1]) as t:
        pkg_files = set(t.getnames())

    # 3a. 包内绝不能有私钥或日志
    leaked_keys = sorted(n for n in pkg_files if "id_ed25519" in n)
    leaked_logs = sorted(n for n in pkg_files if n.endswith(".log"))
    if leaked_keys:
        print(f"    [失败] 迁移包里含 SSH 私钥/公钥：{leaked_keys}")
        ok = False
    if leaked_logs:
        print(f"    [失败] 迁移包里含本机日志：{leaked_logs}")
        ok = False
    if not leaked_keys and not leaked_logs:
        print("    OK  包内无私钥、无本机日志")

    # 3b. 反向核对：包里该有的，git 里是否都有
    missing = sorted(pkg_files - tracked - INTENTIONAL_UNTRACKED)
    if missing:
        print(f"    [失败] 迁移包里有 {len(missing)} 个文件不在 git 中：")
        for m in missing:
            print(f"      - {m}")
        ok = False
    else:
        print(f"    OK  迁移包 {len(pkg_files)} 个文件，除 "
              f"{sorted(INTENTIONAL_UNTRACKED)} 外全部已在 git 中")

force_rm(WORK)

print()
print("=" * 74)
print("结论：", "全新克隆功能完整" if ok else "仍有缺口，见上")
print("=" * 74)
sys.exit(0 if ok else 1)
