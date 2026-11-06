# -*- coding: utf-8 -*-
"""通过 IndexNow 向 Bing / Yandex / Seznam 提交 URL（无需账号登录）。

原理：站点在根路径放一个 <key>.txt（内容即 key），即可证明所有权；
之后任何一次 POST 都能推送 URL 列表。

用法：
  python docs/audit/submit_indexnow.py                 # 默认提交首页
  python docs/audit/submit_indexnow.py <url> [<url>...]

退出码 0 = 提交被接受（200 / 202）
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

from app.api import INDEXNOW_KEY  # noqa: E402  单一事实来源，避免 key 与路由不一致

HOST = "inforadar.xin"
KEY_LOCATION = f"https://{HOST}/{INDEXNOW_KEY}.txt"
ENDPOINT = "https://api.indexnow.org/indexnow"

urls = sys.argv[1:] or [f"https://{HOST}/"]

print("=" * 70)
print("IndexNow 提交")
print("=" * 70)
print(f"  key          : {INDEXNOW_KEY}")
print(f"  keyLocation  : {KEY_LOCATION}")
print(f"  提交 {len(urls)} 个 URL：")
for u in urls:
    print(f"    - {u}")

# 先自检 key 文件是否可访问（IndexNow 会校验，失败会导致 403）
# 注意：Cloudflare 会拦裸 Python-urllib 的 UA（403），这里显式声明一个正常 UA。
CHECK_UA = "Mozilla/5.0 (compatible; InfoRadar-IndexNow/1.0)"
try:
    with urllib.request.urlopen(
            urllib.request.Request(KEY_LOCATION, headers={"User-Agent": CHECK_UA}),
            timeout=20) as r:
        served = r.read().decode("utf-8", "replace").strip()
    key_ok = served == INDEXNOW_KEY
    print(f"\n  key 文件校验: HTTP {r.status}，内容{'匹配' if key_ok else '不匹配！'}")
except urllib.error.HTTPError as exc:
    key_ok = False
    hint = "（Cloudflare 拦了该 UA？用浏览器/机器人 UA 试）" if exc.code == 403 else ""
    print(f"\n  key 文件校验失败: HTTP {exc.code} {hint}")
except Exception as exc:
    key_ok = False
    print(f"\n  key 文件校验失败: {exc}")

if not key_ok:
    print("\n  [中止] key 文件不可用或内容不符，提交必然被拒。")
    sys.exit(1)

payload = {
    "host": HOST,
    "key": INDEXNOW_KEY,
    "keyLocation": KEY_LOCATION,
    "urlList": urls,
}
req = urllib.request.Request(
    ENDPOINT,
    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    headers={"Content-Type": "application/json; charset=utf-8",
             "User-Agent": "InfoRadar-IndexNow/1.0"},
    method="POST",
)

print()
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        status, body = r.status, r.read().decode("utf-8", "replace")
except urllib.error.HTTPError as e:
    status, body = e.code, e.read().decode("utf-8", "replace")
except Exception as exc:
    print(f"  [失败] 请求异常: {exc}")
    sys.exit(1)

print(f"  HTTP {status}")
if body.strip():
    print(f"  响应: {body[:300]}")

MEANING = {
    200: "OK —— URL 已提交",
    202: "Accepted —— 已接收，等待处理",
    400: "Bad Request —— 格式错误",
    403: "Forbidden —— key 校验失败（keyLocation 不可访问或内容不符）",
    422: "Unprocessable —— URL 不属于该 host，或数量超限",
    429: "Too Many Requests —— 提交过于频繁",
}
print(f"  含义: {MEANING.get(status, '未知状态')}")
print()
sys.exit(0 if status in (200, 202) else 1)
