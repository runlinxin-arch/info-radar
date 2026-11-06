# -*- coding: utf-8 -*-
"""评审报告自查：确认报告里的每一条断言都有据可查。

用法： python docs/audit/verify_report_claims.py
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(rel):
    p = os.path.join(BASE, rel)
    return open(p, "r", encoding="utf-8").read() if os.path.isfile(p) else ""


html = read("static/index.html")
api = read("app/api.py")
config = read("config.yaml")

checks = []

# 1. 前端是否真的没用到 /api/search/history
checks.append((
    "前端未调用 /api/search/history（可安全删除该路由）",
    "search/history" not in html,
    f"index.html 中出现次数: {html.count('search/history')}",
))

# 2. 是否有前端路由能力
checks.append((
    "前端无 pushState/replaceState/hash 路由",
    not re.search(r"pushState|replaceState", html),
    f"pushState 出现次数: {len(re.findall('pushState', html))}",
))

# 3. 卡片标题是否有 overflow-wrap / word-break
card_h2 = ""
m = re.search(r"\.card h2 \{(.*?)\}", html, re.S)
if m:
    card_h2 = m.group(1)
checks.append((
    "卡片标题无 overflow-wrap/word-break（长英文会撑破）",
    not re.search(r"overflow-wrap|word-break|word-wrap", card_h2),
    f".card h2 规则: {card_h2.strip()[:90]}",
))

# 4. prefers-reduced-motion 是唯一 @media
medias = re.findall(r"@media[^{]*", html)
checks.append((
    "全站仅 1 个 @media 且是 prefers-reduced-motion",
    len(medias) == 1 and "prefers-reduced-motion" in medias[0],
    f"@media 清单: {[x.strip() for x in medias]}",
))

# 5. 下拉菜单只有 hover 触发
checks.append((
    "子板块下拉仅由 :hover 触发（触屏风险）",
    ".tab-wrap:hover .dropdown" in html and ".tab-wrap:focus-within .dropdown" not in html
    and not re.search(r"tab-wrap'\)\.onclick|wrap\.onclick", html),
    "无 focus-within / 无 click 触发",
))

# 6. readonly 弹层缺少 dialog 语义
checks.append((
    "阅读弹层无 role=dialog / aria-modal / 焦点陷阱",
    not re.search(r'role="dialog"|aria-modal|inert|focusTrap', html),
    "三项均无",
))

# 7. 精读入口是无 href 的 <a>
checks.append((
    "「精读」入口是无 href 的 <a>（键盘不可达）",
    bool(re.search(r'<a onclick="openReader', html)),
    "index.html:517 附近",
))

# 8. Escape 一键关两层
checks.append((
    "Escape 同时关闭单词气泡与阅读器",
    bool(re.search(r"Escape'\) \{ closeWordPop\(\); closeReader\(\);", html)),
    "index.html:681",
))

# 9. 相对时间 / 时间格式化缺失
checks.append((
    "无相对时间格式化（直接输出原始时间串）",
    not re.search(r"分钟前|小时前|toLocaleString|Intl\.RelativeTimeFormat", html),
    "直接渲染 published_at 字符串",
))

# 10. Tavily 日限额与月额度矛盾
m = re.search(r"SEARCH_DAILY_GLOBAL = (\d+)", api)
daily = int(m.group(1)) if m else None
checks.append((
    f"Tavily 日限已下调：SEARCH_DAILY_GLOBAL={daily}（应 ≤33）",
    daily is not None and daily * 30 <= 1000,
    f"{daily} × 30 = {daily * 30 if daily else '?'} 次/月，额度 1000",
))

# 11. 限流字典死代码（已修复：删除死代码 + 新增 _sweep 定期回收）
checks.append((
    "限流死代码已删除，且存在 _sweep 定期回收",
    not re.search(r"dq\.append\(now\)\s*\n\s*if not dq:", api)
    and bool(re.search(r"def _sweep\(self,\s*now\)", api))
    and "_hits.pop" not in api,
    "_sweep() 已定义；append 后无死代码；无旧 pop 写法",
))

# 12. 配置每请求重载
checks.append((
    "每请求重新读取并解析 config.yaml",
    len(re.findall(r"config = load_config\(\)", api)) >= 4,
    f"load_config() 调用点: {len(re.findall(r'config = load_config', api))} 处",
))

# 13. 无 schema 迁移
db = read("app/db.py")
checks.append((
    "数据层无迁移机制（只有 CREATE TABLE IF NOT EXISTS）",
    "user_version" not in db and "ALTER TABLE" not in db,
    "无 user_version / ALTER TABLE",
))

# 14. 内容保留额度（M0：从"统一 30"改为"默认 300 + 国内新闻 500"）
m = re.search(r"per_section_keep: *(\d+)", config)
m_cn = re.search(r"国内新闻:\s*(\d+)", config)
keep_default = int(m.group(1)) if m else None
keep_cn = int(m_cn.group(1)) if m_cn else None
checks.append((
    f"保留额度已提升：默认 {keep_default}、国内新闻 {keep_cn}（M0 前统一 30）",
    keep_default is not None and keep_default >= 300
    and keep_cn is not None and keep_cn >= 500,
    "per_section_keep + per_section_keep_override",
))

# 15. jinja2 依赖显式声明（M0：避免云上 ModuleNotFoundError）
_req = read("deploy/requirements.txt").lower()
checks.append((
    "jinja2 已显式写入 deploy/requirements.txt",
    "jinja2" in _req,
    "P0 文章页模板依赖；此前只是被别的包带进来",
))

# 16. 抓取与 Web 同进程
checks.append((
    "抓取线程运行在 Web 进程内",
    "threading.Thread(target=_update_loop" in read("run.py"),
    "run.py:78",
))

# 17. 隐私路由已移除（任务 C）
HIST_ROUTE = "/api/search/history"
checks.append((
    f"隐私路由 {HIST_ROUTE} 已从源码移除",
    HIST_ROUTE not in api,
    "api.py 中已无该路由定义",
))

# 18/19. 进程内运行期验证（TestClient，不走公网、不写数据库）
sys.path.insert(0, BASE)
try:
    from fastapi.testclient import TestClient
    import app.api as api_module

    _client = TestClient(api_module.app)
    head_code = _client.head("/healthz").status_code
    hist_code = _client.get(HIST_ROUTE).status_code
    robots_resp = _client.get("/robots.txt")
    sitemap_resp = _client.get("/sitemap.xml")
    feed_resp = _client.get("/feed.xml")
    probe_err = ""
except Exception as exc:  # pragma: no cover
    head_code = hist_code = None
    robots_resp = sitemap_resp = feed_resp = None
    probe_err = f"{type(exc).__name__}: {exc}"

checks.append((
    f"/healthz 支持 HEAD：实际 {head_code}（修复前为 405）",
    head_code in (200, 503),
    "app.api_route(methods=['GET','HEAD'])" if not probe_err else probe_err,
))
checks.append((
    f"运行期确认 {HIST_ROUTE} 返回 {hist_code}（期望 404）",
    hist_code == 404,
    "TestClient 进程内验证" if not probe_err else probe_err,
))

# 20/21/22. 任务 6：站点级入口已实现
def _code(resp):
    return getattr(resp, "status_code", None)


def _text(resp):
    return getattr(resp, "text", "") or ""


checks.append((
    f"任务 6 三个站点级入口均返回 200："
    f"robots={_code(robots_resp)} sitemap={_code(sitemap_resp)} feed={_code(feed_resp)}",
    all(_code(r) == 200 for r in (robots_resp, sitemap_resp, feed_resp))
    if not probe_err else False,
    "TestClient 进程内验证" if not probe_err else probe_err,
))
checks.append((
    "robots.txt 声明了 Sitemap 行（供爬虫发现）",
    "Sitemap: https://inforadar.xin/sitemap.xml" in _text(robots_resp),
    "robots.txt 追加在 Cloudflare 管理段之后",
))
checks.append((
    f"feed.xml 可解析且有条目（{_text(feed_resp).count('<item>')} 条）",
    _text(feed_resp).count("<item>") > 0,
    "RSS 2.0，只出摘要 + 原文链接",
))

# 23. IndexNow 所有权校验文件（Bing / Yandex 免登录提交）
try:
    _indexnow = _client.get(f"/{api_module.INDEXNOW_KEY}.txt")
    indexnow_ok = (_indexnow.status_code == 200
                   and _indexnow.text.strip() == api_module.INDEXNOW_KEY)
    indexnow_detail = (f"HTTP {_indexnow.status_code}，"
                       f"内容{'匹配' if indexnow_ok else '不匹配'}")
except Exception as exc:  # pragma: no cover
    indexnow_ok = False
    indexnow_detail = f"{type(exc).__name__}: {exc}"

checks.append((
    "IndexNow 校验文件可访问且内容匹配（Bing/Yandex 提交用）",
    indexnow_ok,
    indexnow_detail,
))

# 24. 搜索引擎所有权校验文件（static/verify/ 下每个文件都应原样可访问）
try:
    _vdir = os.path.join(BASE, "static", "verify")
    _vnames = sorted(f for f in os.listdir(_vdir)
                     if f.endswith((".html", ".xml"))) if os.path.isdir(_vdir) else []
    _vbad = []
    for _n in _vnames:
        with open(os.path.join(_vdir, _n), "rb") as _fh:
            _want = _fh.read()
        _resp = _client.get(f"/{_n}")
        if _resp.status_code != 200 or _resp.content != _want:
            _vbad.append(f"{_n}(HTTP {_resp.status_code})")
    verify_ok = not _vbad
    verify_detail = ("目录为空，无校验文件" if not _vnames else
                     (f"{len(_vnames)} 个文件全部可访问且内容逐字节一致"
                      if not _vbad else f"异常: {_vbad}"))
except Exception as exc:  # pragma: no cover
    verify_ok = False
    verify_detail = f"{type(exc).__name__}: {exc}"

checks.append((
    "搜索引擎所有权校验文件可原样访问（static/verify/）",
    verify_ok,
    verify_detail,
))

print("=" * 78)
print("评审报告断言自查")
print("=" * 78)
failed = 0
for i, (desc, ok, evidence) in enumerate(checks, 1):
    print(f"  [{i:2}] {'通过' if ok else '不成立'}  {desc}")
    print(f"        证据: {evidence}")
    if not ok:
        failed += 1
print()
print(f"合计 {len(checks)} 条断言，不成立 {failed} 条。")
sys.exit(1 if failed else 0)
