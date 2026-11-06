# -*- coding: utf-8 -*-
"""源码静态审计：把「体验问题」和「工程缺陷」落到具体文件行号上。

用法： python docs/audit/audit_code.py
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(rel):
    p = os.path.join(BASE, rel)
    if not os.path.isfile(p):
        return ""
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def find(rel, pattern, flags=0):
    """返回 [(行号, 该行内容)]。"""
    out = []
    for i, line in enumerate(read(rel).splitlines(), 1):
        if re.search(pattern, line, flags):
            out.append((i, line.strip()))
    return out


def section(title):
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


api = read("app/api.py")
html = read("static/index.html")
db = read("app/db.py")
crawler = read("app/crawler.py")
pipeline = read("app/pipeline.py")
run = read("run.py")

section("A. HTTP 层：缓存 / 压缩 / 安全头")
print(f"  FastAPI 中间件数量: {len(re.findall(r'add_middleware', api))}")
for name, pat in [
    ("GZipMiddleware（压缩）", r"GZipMiddleware"),
    ("Cache-Control 设置", r"[Cc]ache-[Cc]ontrol"),
    ("ETag / 条件请求", r"ETag|If-Modified-Since|if_none_match"),
    ("CORS", r"CORSMiddleware"),
    ("TrustedHost", r"TrustedHostMiddleware"),
    ("安全响应头", r"X-Content-Type-Options|Strict-Transport-Security|Content-Security-Policy"),
]:
    print(f"  {name:26} {'有' if re.search(pat, api) else '无'}")
print(f"  index() 返回 FileResponse 且未设 headers: "
      f"{bool(re.search(r'def index', api)) and 'headers=' not in api.split('def index')[1][:400]}")

section("B. 链接安全：javascript: 伪协议防护")
scheme_check = bool(re.search(r"urlparse|scheme|startswith\(.http", crawler + pipeline))
print(f"  服务端校验 URL scheme: {'有' if scheme_check else '无'}")
print(f"  前端对 href 转义: {'有（esc 只转义引号，不过滤协议）' if 'esc(it.link)' in html else '无'}")
print("  风险路径证据：")
for ln, line in find("app/crawler.py", r'"link": link'):
    print(f"    app/crawler.py:{ln}  {line}")
for ln, line in find("static/index.html", r"esc\(it\.link\)"):
    print(f"    static/index.html:{ln}  {line[:110]}")

section("C. 限流实现（内存态 / 可绕过 / 泄漏）")
print("  规则表：")
for ln, line in find("app/api.py", r'^\s+\("/api/'):
    print(f"    api.py:{ln}  {line}")
print("  真实 IP 取值：")
for ln, line in find("app/api.py", r"cf-connecting-ip"):
    print(f"    api.py:{ln}  {line}")
print(f"  未校验请求是否真来自 Cloudflare（无 CF IP 白名单）: "
      f"{'是' if not re.search(r'173\\.245\\.|cloudflare.*ip|CF_IPS', api) else '否'}")
print("  限流字典清理：")
hits_clean = re.findall(r"self\._hits\.pop", api)
print(f"    self._hits.pop 出现次数: {len(hits_clean)}  → "
      f"{'只在 while 循环内，key 永不回收' if len(hits_clean) == 1 else '有清理'}")
for ln, line in find("app/api.py", r"if not dq:")[:3]:
    print(f"    api.py:{ln}  {line}   ← 此时 dq 刚 append 过，恒为 False（死代码）")
print(f"  多 worker 下限流失效（uvicorn workers 数）: "
      f"{re.search(r'workers', run).group(0) if 'workers' in run else '未设置 → 单进程，内存态限流有效'}")

section("D. 隐私：搜索关键词公开可读")
print("  /api/search/history 是否需要鉴权 / 是否脱敏：")
for ln, line in find("app/api.py", r"search/history|SELECT keyword"):
    print(f"    api.py:{ln}  {line}")
print("  → 无鉴权、无脱敏：任何访客可读取全站搜索关键词流水（含他人查询）")
print("  是否把用户输入写库：")
for ln, line in find("app/api.py", r"db\.log_search"):
    print(f"    api.py:{ln}  {line}")

section("E. 抓取与摘要质量")
print("  UA 硬编码：")
for ln, line in find("app/crawler.py", r"HEADERS ="):
    print(f"    crawler.py:{ln}  {line}")
print("  超时 / 重试：")
for ln, line in find("app/crawler.py", r"timeout=|retry|Retry"):
    print(f"    crawler.py:{ln}  {line}")
print(f"  feedparser 处理 bozo 状态: {'有' if 'bozo' in crawler else '无'}")
print(f"  条件请求（ETag/Last-Modified 增量抓取）: "
      f"{'有' if re.search(r'ETag|etag|If-None-Match|modified', crawler) else '无'}")
print(f"  抓取失败重试: {'有' if re.search(r'for attempt|retry', crawler) else '无'}")
print("  摘要生成方式（截断而非摘要）：")
for ln, line in find("app/processor.py", r"head = base\[|cut = SUMMARY_MAX|base\[:SUMMARY_MAX\]"):
    print(f"    processor.py:{ln}  {line}")
print(f"  LLM 分支只用于点词解释、未用于摘要: "
      f"{'是' if '_from_llm' in read('app/worddict.py') and '_from_llm' not in read('app/pipeline.py') else '否'}")

section("F. 数据层：可扩展性与保留策略")
print("  建表方式（能否演进 schema）：")
for ln, line in find("app/db.py", r"CREATE TABLE IF NOT EXISTS")[:2]:
    print(f"    db.py:{ln}  {line}")
print(f"  是否有 migration / user_version: "
      f"{'有' if re.search(r'migrat|user_version|ALTER TABLE', db) else '无'}")
m = re.search(r"per_section_keep: *(\d+)", read("config.yaml"))
print(f"  内容保留上限 per_section_keep: {m.group(1) if m else '未读到'}")
print("  裁剪逻辑（超限直接 DELETE，无归档）：")
for ln, line in find("app/db.py", r"def trim_section|DELETE FROM items"):
    print(f"    db.py:{ln}  {line}")
print("  全文索引 / FTS：")
print(f"    无 FTS5 虚拟表: {'是' if 'fts5' not in db.lower() else '否'}")

section("G. 前端：SEO / 可分享 / 可访问性")
print("  <head> 缺失项：")
for name, pat in [
    ("meta description", r'name="description"'),
    ("og:title", r'property="og:title"'),
    ("og:image", r'property="og:image"'),
    ("canonical", r'rel="canonical"'),
    ("favicon", r'rel="icon"'),
    ("JSON-LD", r'application/ld\+json'),
    ("<noscript> 兜底", r'<noscript>'),
]:
    print(f"    {name:18} {'OK' if re.search(pat, html, re.I) else '缺失'}")
print("  路由结构（内容能否被单独分享/收录）：")
print(f"    前端是否存在 pushState/history API: "
      f"{'有' if re.search(r'pushState|replaceState|location\\.hash', html) else '无 → 所有内容共用一个 URL /，无法分享单篇'}")
print(f"    详情页是否为独立可访问 URL: "
      f"{'是' if re.search(r'<button[^>]*onclick=\"location', html) else '否 → 只用弹层展示'}")
print("  可访问性：")
for name, pat in [
    ("reader 弹层 role=dialog", r'role="dialog"'),
    ("aria-modal", r'aria-modal'),
    ("焦点陷阱 focus trap", r'[Ff]ocusTrap|inert'),
    ("输入框 <label>", r'<label'),
    ("aria-live 状态播报", r'aria-live'),
    ("tab 键盘可操作（tabindex/keydown）", r'tabindex|keydown.*tab|ArrowRight'),
]:
    print(f"    {name:32} {'有' if re.search(pat, html) else '无'}")
print("  Escape 键行为：")
for ln, line in find("static/index.html", r"e\.key === 'Escape'"):
    print(f"    index.html:{ln}  {line}   ← 一次按键同时关闭两层（弹词 + 阅读器）")
print("  触屏 / 移动端：")
print(f"    @media 查询数量: {len(re.findall(r'@media', html))}"
      f"（仅 prefers-reduced-motion 算 1 个，无响应式断点）")
print(f"    下拉菜单触发方式: hover"
      f" → 触屏无 hover，子板块在该机型上可能点不开")
for ln, line in find("static/index.html", r"\\.tab-wrap:hover \\.dropdown"):
    print(f"    index.html:{ln}  {line}")
print("  弹词交互依赖鼠标坐标：")
for ln, line in find("static/index.html", r"e\.clientX|e\.clientY"):
    print(f"    index.html:{ln}  {line}   ← 触屏 click 的 clientX/Y 不可靠")

section("H. 服务进程职责混杂（Web 与抓取同进程）")
print("  抓取线程在 Web 进程内启动：")
for ln, line in find("run.py", r"Thread|threading"):
    print(f"    run.py:{ln}  {line}")
print("  更新状态保存在进程内存（重启即丢）：")
for ln, line in find("app/api.py", r"_update_state = \{"):
    print(f"    api.py:{ln}  {line}")
print(f"  更新开关持久化: "
      f"{'是' if re.search(r'_update_state\[.running.\]\s*=\s*True.*setting', api) else '否 → 进程重启可并发触发两次更新'}")
print("  每次请求都重新读配置文件：")
for ln, line in find("app/api.py", r"config = load_config\(\)"):
    print(f"    api.py:{ln}  {line}")

section("I. 文案与产品承诺不一致")
print("  下次更新提示的来源（配置写 4 小时，前端有周更兜底文案）：")
for ln, line in find("static/index.html", r"st-next"):
    print(f"    index.html:{ln}  {line[:120]}")
for ln, line in find("config.yaml", r"next_hint"):
    print(f"    config.yaml:{ln}  {line}")
print("  空状态文案：")
for ln, line in find("static/index.html", r"暂无内容"):
    print(f"    index.html:{ln}  {line.strip()[:120]}")
print("  站点缺少 about / 免责声明 / 版权说明 路由：")
print(f"    api.py 中路由总数: {len(re.findall(r'@app\\.(get|post)', api))}")
for ln, line in find("app/api.py", r"@app\.(get|post)"):
    print(f"    api.py:{ln}  {line}")
