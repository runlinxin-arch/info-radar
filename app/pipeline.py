# -*- coding: utf-8 -*-
"""全板块更新流水线：RSS 抓取 → 正文提取 → 摘要 → 去重 → 入库 → 裁剪。"""
import logging

from . import crawler, db, processor

log = logging.getLogger("pipeline")


def run_update(config, progress_cb=None):
    """执行一次全量更新，返回 (新增总数, [错误信息])。

    progress_cb(msg) 可选，用于报告进度。
    """
    def report(msg):
        log.info(msg)
        if progress_cb:
            progress_cb(msg)

    db.init_db()

    # 同步 sources 表
    for s in config.get("sources", []):
        db.upsert_source(s["name"], s["section"], s["url"],
                         s.get("type", "rss"), 1 if s.get("enabled", True) else 0)

    keep = int(config.get("per_section_keep", 30))
    fetch_content = bool(config.get("fetch_full_content", True))
    sources = db.get_enabled_sources()

    # 每个源的抓取条数按板块内源数量分摊，使板块总量与 keep 相当，
    # 避免"抓得多、裁剪掉、下次又当新条目抓回"的抖动。
    from collections import Counter
    section_counts = Counter(s["section"] for s in sources)

    total_new = 0
    errors = []
    for i, src in enumerate(sources, 1):
        report(f"[{i}/{len(sources)}] 抓取 {src['section']} / {src['name']}")
        per_source = max(5, keep // section_counts[src["section"]])
        try:
            items = crawler.crawl_source(src, max_entries=per_source,
                                         fetch_content=fetch_content)
        except Exception as e:
            items = None
            log.exception("源处理异常 %s", src["url"])
        if items is None:
            errors.append(f"{src['name']}: 抓取失败")
            continue
        recent_titles = db.get_recent_titles(src["section"])
        new_count = 0
        for it in items:
            if db.item_exists(it["link"]):
                continue
            if processor.is_duplicate_title(it["title"], recent_titles):
                continue
            if db.insert_item(**it):
                recent_titles.append(it["title"])
                new_count += 1
        db.trim_section(src["section"], keep)
        total_new += new_count
        report(f"    {src['name']} 新增 {new_count} 条")

    db.set_setting("last_update", db.now_str())
    db.set_setting("last_update_new_count", total_new)
    return total_new, errors
