# -*- coding: utf-8 -*-
"""线上验收：确认 /healthz 探针经过 Cloudflare + 隧道后行为正确。

这个脚本模拟外部监控（UptimeRobot）的视角：
用监控的 UA、从公网、走完整链路打一次。

用法： python docs/audit/check_healthz_live.py
退出码 0 = 健康可挂监控；1 = 当前不健康（或探针不存在）
"""
import json
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://inforadar.xin"
# 用监控服务常见的请求特征，验证它不会因为 UA / Accept 被特殊对待
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; UptimeRobot/2.0; http://www.uptimerobot.com/)",
    "Accept": "*/*",
    "Cache-Control": "no-cache",
}


def get(path):
    req = urllib.request.Request(BASE + path, headers=HEADERS)
    try:
        r = urllib.request.urlopen(req, timeout=25)
        return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")
    except Exception as e:
        return None, {}, f"ERR {type(e).__name__}: {e}"


print("=" * 74)
print(f"线上探针验收：{BASE}/healthz")
print("=" * 74)

status, headers, body = get("/healthz")
print(f"  HTTP 状态 : {status}")
print(f"  cf-cache  : {headers.get('cf-cache-status', headers.get('CF-Cache-Status', '-'))}"
      "   （理想值为 DYNAMIC，说明没有被缓存成陈旧结果）")
print(f"  Content-Type: {headers.get('Content-Type', '-')}")
print(f"  响应体    : {body[:220]}")

verdict = 0
if status is None:
    print("\n  [失败] 完全打不通 —— 这正是监控会告警的情形（隧道/源站不可达）")
    verdict = 1
elif status == 200:
    try:
        d = json.loads(body)
    except ValueError:
        print("\n  [失败] 200 但不是 JSON，探针可能没被正确路由")
        verdict = 1
    else:
        if d.get("ok") is True:
            print(f"\n  [通过] ok=true，reason={d.get('reason')}，"
                  f"距上次更新 {d.get('hours_since')} 小时")
            print("         → 可以把这个 URL 填进 UptimeRobot，判定规则：2xx 为 up")
        else:
            print(f"\n  [不健康] ok=false，reason={d.get('reason')}")
            print("         → 探针工作正常，但站点内容确实已陈旧，需要触发一次更新")
            verdict = 1
elif status == 503:
    try:
        d = json.loads(body)
        print(f"\n  [预期行为] 503 ok=false reason={d.get('reason')} "
              f"hours_since={d.get('hours_since')}")
        print("         → 探针正确地在「内容陈旧」时返回 503，监控会因此告警。")
        print("         → 当前站点确实需要一次更新：curl -X POST http://127.0.0.1:7100/api/update")
    except ValueError:
        print("\n  [注意] 503 但不是我们返回的 JSON（可能是 Cloudflare 或反代错误页）")
    verdict = 1
else:
    print(f"\n  [失败] 非预期状态码 {status}")
    verdict = 1

# 顺带确认整站可达性
print()
s2, _, _ = get("/")
print(f"  对照：GET / → HTTP {s2}")

print()
print("=" * 74)
print("结论：", "探针可用，可以挂监控" if verdict == 0 else "探针当前不适合挂监控（见上）")
print("=" * 74)
sys.exit(verdict)
