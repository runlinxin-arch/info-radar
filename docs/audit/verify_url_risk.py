# -*- coding: utf-8 -*-
"""安全校验实验：恶意/异常 feed 链接会如何流到前端 href。

用法： python docs/audit/verify_url_risk.py
不联网，纯本地复现渲染链路。
"""
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

# ---------- 复刻 static/index.html 里的 esc() ----------
_ESC = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}


def esc(s):
    return re.sub(r"[&<>\"']", lambda m: _ESC[m.group(0)], s or "")


def normalized_scheme(url):
    """浏览器解析 href 时的等效 scheme（去首尾空白 + 转小写）。"""
    return url.strip().lower()


CONFIRMED = ("javascript:", "vbscript:", "data:")


# ---------- 复刻 static/index.html 里的卡片模板 ----------
def render_card(it):
    return (f'<a href="{esc(it["link"])}" target="_blank" rel="noopener">'
            f'{esc(it["title"])}</a>')


# ---------- 复刻 crawler.fetch_feed 对 link 的处置 ----------
def crawler_accepts(link):
    """crawler.py 第 28-44 行：只判非空，不改写、不校验协议。"""
    title = "恶意条目"
    if not title or not link:
        return None
    return {"title": title, "link": link.strip()}


CASES = [
    ("正常 https", "https://www.geekpark.net/news/12345"),
    ("正常 http", "http://example.com/a"),
    ("javascript 伪协议", "javascript:fetch('/api/update',{method:'POST'})"),
    ("javascript + 大小写混淆", "JaVaScRiPt:alert(1)"),
    ("data: URI", "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg=="),
    ("vbscript:", "vbscript:msgbox(1)"),
    ("属性逃逸尝试（引号）", 'https://x.com/" onmouseover="alert(1)'),
    ("前导空白绕过", "  javascript:alert(1)"),
    ("tab/换行绕过", "java\tscript:alert(1)"),
]

print("=" * 78)
print("1. crawler 是否拦下异常 link")
print("=" * 78)
accepted = []
for name, link in CASES:
    item = crawler_accepts(link)
    ok = item is not None
    if ok:
        accepted.append((name, link))
    print(f"  {name:24} crawler 接受: {'是' if ok else '否'}")

print()
print("=" * 78)
print("2. 接受后渲染成 HTML 的实际结果")
print("=" * 78)
for name, link in accepted:
    html = render_card({"title": "恶意条目", "link": link})
    m = re.search(r'href="([^"]*)"', html)
    href = m.group(1) if m else "(解析失败)"
    danger = ""
    if normalized_scheme(link).startswith(CONFIRMED):
        danger = "  <== 危险：可执行伪协议原样进入 href"
    elif '"' in link or "'" in link or "<" in link or ">" in link:
        danger = "  （引号已被 esc 转义为实体，属性未被逃逸）"
    print(f"  {name}")
    print(f"    href 实际值: {href!r}{danger}")

print()
print("=" * 78)
print("3. 结论")
print("=" * 78)
confirmed = [n for n, l in accepted
             if normalized_scheme(l).startswith(CONFIRMED)]
print(f"  crawler 放行的用例: {len(accepted)}/{len(CASES)}（只判非空，无协议白名单）")
print(f"  确认渲染后仍是可执行伪协议: {confirmed}")
print(f"  引号逃逸（属性注入）: {'未发生，esc() 生效' if not any('onmouseover=' in esc(l) and '&quot;' not in esc(l) for _, l in accepted) else '发生'}")
print()
print("  要点：")
print("   - esc() 挡住了引号逃逸/属性注入，这点是好的。")
print("   - 但整条链路没有任何协议白名单：crawler 收、db 存、前端 href 直用。")
print("   - 浏览器会忽略 href 首尾空白，所以 '  javascript:...' 等效于 'javascript:...'。")
print("   - 攻击面：任一被聚合的第三方 RSS 源提供 javascript:/data: 链接，")
print("     访客点击即在本站同源下执行脚本（可读改站点数据、触发 /api/update）。")
print("   - 修复：落库前只放行 http/https；前端渲染 href 前再校验一次（纵深防御）。")
