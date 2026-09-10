# -*- coding: utf-8 -*-
"""规则式摘要与去重。

摘要策略：取正文前 300~500 字（尽量在句号处截断），并附加含关键词的关键句；
正文缺失时退化为 RSS summary 清洗后的截断。
去重：URL 精确去重（数据库 UNIQUE）+ 板块内近期标题相似度去重。
"""
import re
from difflib import SequenceMatcher

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")

SUMMARY_MIN = 300
SUMMARY_MAX = 500

# 简单关键词表：命中这些词的句子优先作为"关键句"
KEYWORDS = [
    "发布", "推出", "宣布", "研究", "突破", "模型", "开源", "融资", "发现",
    "report", "release", "launch", "announce", "study", "research",
    "breakthrough", "model", "AI", "according",
]


def clean_text(text):
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text)
    return text.strip()


def _split_sentences(text):
    parts = re.split(r"(?<=[。！？.!?])\s*", text)
    return [p.strip() for p in parts if p.strip()]


def make_summary(content, rss_summary=""):
    """生成 300~500 字摘要：正文开头 + 关键句；正文不足时用 rss_summary。"""
    content = clean_text(content)
    rss_summary = clean_text(rss_summary)
    base = content if len(content) >= 120 else rss_summary
    if not base:
        return ""
    if len(base) <= SUMMARY_MAX:
        return base

    head = base[:SUMMARY_MAX]
    # 尽量在 SUMMARY_MIN 之后的第一个句末标点处截断
    cut = -1
    for m in re.finditer(r"[。！？.!?]", head):
        if m.start() >= SUMMARY_MIN:
            cut = m.start() + 1
            break
    if cut == -1:
        cut = SUMMARY_MAX
    summary = head[:cut]

    # 从剩余正文中挑一条含关键词的关键句补充（若还有空间）
    rest = base[cut:]
    for sent in _split_sentences(rest):
        if any(k in sent for k in KEYWORDS) and 10 <= len(sent) <= 160:
            if len(summary) + len(sent) <= SUMMARY_MAX:
                summary += sent
            break
    return summary


def title_similarity(a, b):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def is_duplicate_title(title, existing_titles, threshold=0.85):
    return any(title_similarity(title, t) >= threshold for t in existing_titles)
