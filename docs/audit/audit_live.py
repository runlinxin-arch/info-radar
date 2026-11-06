# -*- coding: utf-8 -*-
"""线上站点体检：SEO / 发现资源 / 缓存头 / 首屏渲染 / 移动端就绪度。

用法： python docs/audit/audit_live.py
"""
import re
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://inforadar.xin"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
H = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}


def get(path):
    req = urllib.request.Request(BASE + path, headers=H)
    try:
        r = urllib.request.urlopen(req, timeout=25)
        return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), ""
    except Exception as e:
        return None, {}, f"ERR {type(e).__name__}: {e}"


print("=" * 78)
print("1. 发现资源 / 路由可用性")
print("=" * 78)
for p in ["/", "/robots.txt", "/sitemap.xml", "/feed.xml", "/rss.xml",
          "/favicon.ico", "/apple-touch-icon.png", "/manifest.json",
          "/about", "/about/", "/privacy", "/archives", "/page/2",
          "/nonexistent-page-xyz", "/api/idioms"]:
    st, hd, body = get(p)
    ct = hd.get("Content-Type", "-")
    cc = hd.get("Cache-Control", "-")
    cf = hd.get("cf-cache-status", "-")
    flag = ""
    if p == "/nonexistent-page-xyz" and st == 200:
        flag = "  <-- 404 页返回 200（软 404，搜索引擎会判低质）"
    if st == 200 and p.startswith("/api/"):
        flag = f"  len={len(body)}"
    print(f"  {p:24} {str(st):5} {ct[:28]:30} cache={cc[:24]:26} cf={cf}{flag}")

print()
print("=" * 78)
print("2. 首页响应头（缓存 / 压缩 / 安全头）")
print("=" * 78)
st, hd, html = get("/")
for k in sorted(hd):
    print(f"  {k}: {hd[k]}")
print()
print("  安全头检查：")
for k in ["Strict-Transport-Security", "X-Content-Type-Options",
          "X-Frame-Options", "Referrer-Policy", "Content-Security-Policy",
          "Permissions-Policy"]:
    print(f"    {k:32} {'OK' if k in hd else '缺失'}")

print()
print("=" * 78)
print("3. 首页 <head> 元信息")
print("=" * 78)
head = html[:html.find("</head>")] if "</head>" in html else html
checks = {
    "meta description": r'<meta[^>]+name=["\']description',
    "meta robots": r'<meta[^>]+name=["\']robots',
    "og:title": r'property=["\']og:title',
    "og:description": r'property=["\']og:description',
    "og:image": r'property=["\']og:image',
    "og:url": r'property=["\']og:url',
    "twitter:card": r'name=["\']twitter:card',
    "canonical": r'rel=["\']canonical',
    "favicon": r'rel=["\'](?:icon|shortcut icon)',
    "lang 属性": r'<html[^>]+lang=',
    "viewport": r'name=["\']viewport',
    "charset": r'charset=',
    "JSON-LD 结构化数据": r'application/ld\+json',
}
for name, pat in checks.items():
    print(f"  {name:22} {'OK' if re.search(pat, head, re.I) else '缺失'}")

print()
print("=" * 78)
print("4. 首屏是否有服务端渲染内容（SEO 决定性）")
print("=" * 78)
body = html[html.find("<body"):] if "<body" in html else ""
m = re.search(r"<main[^>]*>(.*?)</main>", body, re.S)
inner = (m.group(1).strip() if m else "")
print(f"  <main> 内首屏内容长度: {len(inner)} 字符")
print(f"  内容片段: {inner[:120]!r}")
print(f"  含 '加载中': {'加载中' in body}")
print(f"  含 .card 元素: {'class=\"card\"' in body}")
print(f"  含真实标题 <h2>: {'<h2>' in body}")
print(f"  含 <noscript>: {'<noscript>' in body}")
print("  => 搜索引擎抓到的首屏正文 =", "空" if '<h2>' not in body else "有内容")

print()
print("=" * 78)
print("5. HTML 体积与内联资源（缓存友好度）")
print("=" * 78)
print(f"  首页 HTML: {len(html)} 字符 / {len(html.encode('utf-8'))} 字节")
style_len = sum(len(x) for x in re.findall(r"<style[^>]*>(.*?)</style>", html, re.S))
script_len = sum(len(x) for x in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S))
print(f"  内联 <style> 合计: {style_len} 字符")
print(f"  内联 <script> 合计: {script_len} 字符")
ext = re.findall(r'(?:src|href)=["\']((?:https?:)?//[^"\']+\.(?:js|css|png|jpg|svg|webp|ico))', html, re.I)
print(f"  外部静态资源引用: {sorted(set(ext)) or '无（全部内联）'}")

print()
print("=" * 78)
print("6. 移动端 / 可访问性静态信号")
print("=" * 78)
sig = {
    "响应式断点 @media": len(re.findall(r"@media", html)),
    "aria-* 属性": len(re.findall(r"\baria-[a-z]+=", html)),
    "role= 属性": len(re.findall(r"\brole=", html)),
    "<button> 元素": len(re.findall(r"<button", html)),
    "onclick= 内联事件": len(re.findall(r"onclick=", html)),
    "可聚焦 div/a 无 href": len(re.findall(r'<a onclick=', html)),
    "skip-link": len(re.findall(r"skip", html, re.I)),
}
for k, v in sig.items():
    print(f"  {k:26} {v}")
print(f"  prefers-reduced-motion 支持: {'OK' if 'prefers-reduced-motion' in html else '缺失'}")
