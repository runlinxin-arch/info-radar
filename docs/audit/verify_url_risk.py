# -*- coding: utf-8 -*-
"""外链协议防护：修复前 vs 修复后的对照实验。

任务 C 之前，这个脚本复刻旧逻辑并证明 9/9 恶意用例被放行；
任务 C 之后，它改为**同时**跑「旧逻辑复刻」与「当前真实实现」，
用来证明修复真的生效，并且不影响合法链接。

用法： python docs/audit/verify_url_risk.py
退出码 0 = 当前实现已拦住全部可执行伪协议
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

from app.crawler import safe_link  # 当前真实实现（任务 C 新增）

# ---------- 修复前的逻辑（保留为对照基线）----------
_ESC = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}


def esc(s):
    return re.sub(r"[&<>\"']", lambda m: _ESC[m.group(0)], s or "")


def old_accepts(link):
    """任务 C 之前的 crawler：只判非空，不改写、不校验协议。"""
    return link.strip() if (link or "").strip() else None


def old_render(link):
    """任务 C 之前的卡片模板：esc 只转义引号，不过滤协议。"""
    return f'<a href="{esc(link)}" target="_blank" rel="noopener">标题</a>'


EXECUTABLE = ("javascript:", "vbscript:", "data:")


def effective_scheme(url):
    """浏览器解析 href 时的等效 scheme（忽略首尾空白、大小写）。"""
    return (url or "").strip().lower()


CASES = [
    ("正常 https", "https://www.geekpark.net/news/12345"),
    ("正常 http", "http://example.com/a"),
    ("javascript 伪协议", "javascript:fetch('/api/update',{method:'POST'})"),
    ("javascript 大小写混淆", "JaVaScRiPt:alert(1)"),
    ("data: URI", "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg=="),
    ("vbscript:", "vbscript:msgbox(1)"),
    ("属性逃逸尝试（引号）", 'https://x.com/" onmouseover="alert(1)'),
    ("前导空白绕过", "  javascript:alert(1)"),
    ("tab 分隔绕过", "java\tscript:alert(1)"),
    ("相对路径（部分 feed 会出现）", "/article/1"),
]

print("=" * 86)
print("外链协议防护对照实验")
print("=" * 86)
print(f"  {'用例':<26}{'旧逻辑':<10}{'当前实现':<12}结论")
print("-" * 86)

old_bad, new_bad, changed = [], [], []
for name, link in CASES:
    o = old_accepts(link)
    n = safe_link(link)
    dangerous = effective_scheme(link).startswith(EXECUTABLE)

    if o and dangerous:
        old_bad.append(name)
    if n and dangerous:
        new_bad.append(name)
    if bool(o) != bool(n):
        changed.append(name)

    if dangerous:
        note = "危险已被拦住" if not n else "仍然危险！"
    elif not n:
        note = ("非 http(s) 变体，被拒" if not effective_scheme(link).startswith(
            ("http://", "https://")) else "合法但被拒（需人工判断）")
    else:
        note = "正常"
    print(f"  {name:<26}{'放行' if o else '拒绝':<10}{'放行' if n else '拒绝':<12}{note}")

# 旧实现渲染后 href 里是什么
print()
print("旧实现渲染结果（证明当时确实可执行）：")
shown = 0
for name, link in CASES:
    if old_accepts(link) and effective_scheme(link).startswith(EXECUTABLE):
        href = re.search(r'href="([^"]*)"', old_render(link)).group(1)
        print(f"  {name:<26} href={href[:56]!r}")
        shown += 1
if not shown:
    print("  （无）")

# 前端纵深防御
html = open(os.path.join(BASE, "static", "index.html"), encoding="utf-8").read()
validated = len(re.findall(r'href="\$\{esc\(href\)\}"', html))
print()
print("前端纵深防御：")
print(f"  定义了 safeUrl()                 : {'是' if re.search(r'function\s+safeUrl\s*\(', html) else '否'}")
print(f"  it.link 仍直接进入 href          : {'是（危险）' if re.search(r'esc\(it\.link\)', html) else '否'}")
print(f"  取自校验变量的 href 数量          : {validated}")

print()
print("=" * 86)
print(f"  旧实现放行可执行伪协议 : {len(old_bad)} 条  {old_bad}")
print(f"  当前实现放行可执行伪协议: {len(new_bad)} 条  {new_bad}")
if changed:
    print(f"  判定发生变化的用例      : {changed}")
print("=" * 86)
print()
print("说明：相对路径以前会渲染成指向本站的坏链接（/article/1 打到 inforadar.xin），")
print("      现在直接不展示，属于改进而非退化。")
sys.exit(0 if not new_bad else 1)
