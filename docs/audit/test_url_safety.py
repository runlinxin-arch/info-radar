# -*- coding: utf-8 -*-
"""回归测试：外链协议白名单（app.crawler.safe_link）。

对应任务 C 的第 1、3 条改动。直接 import 真实实现，不复制逻辑，
否则测试与代码会各自漂移。

用法： python docs/audit/test_url_safety.py
退出码 0 = 全部通过
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

from app.crawler import safe_link  # noqa: E402

# (说明, 输入, 期望输出)  —— None 表示应被拒绝
CASES = [
    # ---------- 应放行 ----------
    ("正常 https", "https://www.geekpark.net/news/12345",
     "https://www.geekpark.net/news/12345"),
    ("正常 http", "http://example.com/a", "http://example.com/a"),
    ("首尾空白应被 strip 后放行", "  https://x.com/a  ", "https://x.com/a"),
    ("带查询串", "https://x.com/a?b=1&c=2", "https://x.com/a?b=1&c=2"),
    ("大写 scheme 也应放行", "HTTPS://x.com/a", "HTTPS://x.com/a"),
    ("中文路径", "https://zh.wikipedia.org/wiki/信息", "https://zh.wikipedia.org/wiki/信息"),

    # ---------- 应拒绝 ----------
    ("javascript 伪协议", "javascript:fetch('/api/update',{method:'POST'})", None),
    ("javascript 大小写混淆", "JaVaScRiPt:alert(1)", None),
    ("前导空白的 javascript", "  javascript:alert(1)", None),
    ("tab 分隔的 javascript", "java\tscript:alert(1)", None),
    ("换行分隔的 javascript", "java\nscript:alert(1)", None),
    ("data: URI", "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==", None),
    ("vbscript:", "vbscript:msgbox(1)", None),
    ("file:", "file:///C:/Windows/win.ini", None),
    ("ftp:", "ftp://example.com/x", None),
    ("mailto:", "mailto:a@b.com", None),
    ("协议相对地址（无 scheme）", "//example.com/a", None),
    ("纯相对路径", "/article/1", None),
    ("空串", "", None),
    ("全空白", "   ", None),
    ("None", None, None),
    ("非字符串（int）", 123, None),
    ("非字符串（list）", ["https://x.com"], None),
]

# 引号等 HTML 注入素材：协议合法，交由前端 esc() 转义，不应在这里被误杀
QUOTE_CASE = 'https://x.com/" onmouseover="alert(1)'


def check(desc, given, want):
    got = safe_link(given)
    ok = got == want
    shown = repr(got)
    if len(shown) > 58:
        shown = shown[:55] + "..."
    print(f"  [{'通过' if ok else '失败'}] {desc:<30} -> {shown}")
    if not ok:
        print(f"         期望: {want!r}")
    return ok


print("=" * 76)
print("外链协议白名单测试：app.crawler.safe_link")
print("=" * 76)

failed = 0
for desc, given, want in CASES:
    if not check(desc, given, want):
        failed += 1

# 合法但含引号：应放行（注入防护是 esc 的职责）
got = safe_link(QUOTE_CASE)
ok = got == QUOTE_CASE
if not ok:
    failed += 1
print(f"  [{'通过' if ok else '失败'}] {'引号素材仍属 http，应放行':<30} -> "
      f"{'放行' if got else '被拒'}")
if not ok:
    print("         期望放行：引号由前端 esc() 转义，不是协议问题")

# ---- 接线检查：fetch_feed 真的用了 safe_link，而不是只定义没用 ----------
print()
print("接线检查（防止「函数写了但没接上」）：")
crawler_src = open(os.path.join(BASE, "app", "crawler.py"), encoding="utf-8").read()

wired = re.search(r"link\s*=\s*safe_link\(e\.get\(\s*[\"']link[\"']\s*\)\)", crawler_src)
old = re.search(r"link\s*=\s*\(e\.get\(\s*[\"']link[\"']\s*\)\s*or\s*[\"']{2}\)\.strip\(\)",
                crawler_src)
for desc, ok in [
    ("fetch_feed 使用 safe_link", bool(wired)),
    ("旧的裸 strip 赋值已移除", not old),
]:
    if not ok:
        failed += 1
    print(f"  [{'通过' if ok else '失败'}] {desc}")

# ---- 前端接线：三处 href 都必须经过 safeUrl 校验 ---------------------------
html = open(os.path.join(BASE, "static", "index.html"), encoding="utf-8").read()
print()
print("前端接线检查（断言「渲染安全性」，不是断言某一行怎么写）：")

# 三处渲染的外链：列表标题、列表「阅读原文」、阅读器「阅读原文」
# 它们都必须从经过 safeUrl 校验的 href 变量取值
validated_hrefs = len(re.findall(r'href="\$\{esc\(href\)\}"', html))
calls = len(re.findall(r"safeUrl\(it\.link\)", html))

frontend_checks = [
    ("定义了 safeUrl()", bool(re.search(r"function\s+safeUrl\s*\(", html))),
    ("三处 href 均取自校验后的 href 变量", validated_hrefs == 3),
    ("it.link 不再直接进入任何 href", not re.search(r"esc\(it\.link\)", html)),
    ("标题在无合法链接时退化为纯文本", bool(re.search(r":\s*esc\(it\.title\)", html))),
    ("阅读器原文入口为条件渲染", bool(re.search(r"\$\{href \?", html))),
    ("阅读按钮仍走 openReader（未被误改）",
     bool(re.search(r'href="javascript:void\(0\)" onclick="openReader', html))),
]
for desc, ok in frontend_checks:
    if not ok:
        failed += 1
    extra = ""
    if "三处 href" in desc:
        extra = f"（实际 {validated_hrefs} 处 href 取自 href 变量；safeUrl 调用 {calls} 次）"
    print(f"  [{'通过' if ok else '失败'}] {desc}{extra}")

total = len(CASES) + 1 + 2 + len(frontend_checks)
print()
print(f"合计 {total} 项，失败 {failed} 项。")
sys.exit(1 if failed else 0)
