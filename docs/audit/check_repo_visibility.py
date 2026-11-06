# -*- coding: utf-8 -*-
"""检查 GitHub 仓库可见性（公开仓库里出现密钥就是事故）。

用法： python docs/audit/check_repo_visibility.py
"""
import json
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

REPO = "runlinxin-arch/info-radar"
API = f"https://api.github.com/repos/{REPO}"
H = {"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github+json"}

print(f"检查仓库：{REPO}")
print("=" * 60)
try:
    r = urllib.request.urlopen(urllib.request.Request(API, headers=H), timeout=20)
    d = json.loads(r.read().decode())
    private = d.get("private")
    print(f"  HTTP {r.status}")
    print(f"  private = {private}  ->  {'私有仓库（安全）' if private else '公开仓库（任何泄露的密钥都等于已泄露）'}")
    print(f"  default_branch = {d.get('default_branch')}")
    print(f"  pushed_at = {d.get('pushed_at')}")
    print(f"  visibility = {d.get('visibility')}")
except urllib.error.HTTPError as e:
    if e.code == 404:
        print("  HTTP 404 -> 匿名不可见，通常意味着私有仓库（或无此仓库）")
        print("  注：私有仓库对匿名请求返回 404，这是 GitHub 的标准行为。")
    else:
        print(f"  HTTP {e.code}: {e.reason}")
except Exception as e:
    print(f"  ERR {type(e).__name__}: {e}")
