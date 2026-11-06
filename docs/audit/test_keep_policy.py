# -*- coding: utf-8 -*-
"""M0 回归测试：分板块保留额度（per_section_keep_override）。

背景：实测国内新闻 30 条只覆盖 3.7 小时，而学术板块 30 条能覆盖一天以上。
统一额度会让快板块被反复冲刷，所以 M0 把它改成「默认值 + 板块覆盖」。

用法： python docs/audit/test_keep_policy.py
退出码 0 = 全部通过
"""
import os
import re
import sys

import yaml

sys.stdout.reconfigure(encoding="utf-8")

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

from app.pipeline import DEFAULT_KEEP, keep_for_section  # noqa: E402

failed = 0
total = 0


def check(desc, ok, extra=""):
    global failed, total
    total += 1
    if not ok:
        failed += 1
    print(f"  [{'通过' if ok else '失败'}] {desc}{extra}")


print("=" * 76)
print("分板块保留额度：keep_for_section()")
print("=" * 76)

# ---------- 纯函数行为 ----------
check("无 override 时回落默认值",
      keep_for_section({"per_section_keep": 300}, "世界新闻") == 300)
check("命中 override 时用覆盖值",
      keep_for_section({"per_section_keep": 300,
                        "per_section_keep_override": {"国内新闻": 500}},
                       "国内新闻") == 500)
check("字符串数字也能解析",
      keep_for_section({"per_section_keep": "300",
                        "per_section_keep_override": {"国内新闻": "500"}},
                       "国内新闻") == 500)
check("override 非法值 → 回落默认",
      keep_for_section({"per_section_keep": 300,
                        "per_section_keep_override": {"国内新闻": "abc"}},
                       "国内新闻") == 300)
check("override 为 0 → 回落默认（不能保留 0 条）",
      keep_for_section({"per_section_keep": 300,
                        "per_section_keep_override": {"国内新闻": 0}},
                       "国内新闻") == 300)
check("override 为负数 → 回落默认",
      keep_for_section({"per_section_keep": 300,
                        "per_section_keep_override": {"国内新闻": -5}},
                       "国内新闻") == 300)
check("完全缺配置时用 DEFAULT_KEEP",
      keep_for_section({}, "任意板块") == DEFAULT_KEEP,
      f"（DEFAULT_KEEP={DEFAULT_KEEP}）")
check("override 是 None（YAML 空键）不炸",
      keep_for_section({"per_section_keep": 300,
                        "per_section_keep_override": None}, "国内新闻") == 300)

# ---------- 真实配置 ----------
print()
print("真实 config.yaml 解析结果：")
cfg_path = os.path.join(BASE, "config.yaml")
cfg = yaml.safe_load(open(cfg_path, encoding="utf-8")) if os.path.isfile(cfg_path) else {}

EXPECT = {
    "国内新闻": 500,
    "世界新闻": 300,
    "AI 资讯": 300,
    "学术 · AI/CS": 300,
    "学术 · 交互设计": 300,
    "学术 · 心理学": 300,
}
capacity = 0
for section, want in EXPECT.items():
    got = keep_for_section(cfg, section)
    capacity += got
    check(f"{section} → {got}（期望 {want}）", got == want)

check("每板块额度都 ≥ 100（不再有 30 这种量级）",
      all(keep_for_section(cfg, s) >= 100 for s in EXPECT))
check(f"全站容量 {capacity} 条 ≥ 1800（原先 180）", capacity >= 1800)

# ---------- 源码回归：确认旧的单值逻辑已被替换 ----------
print()
print("源码回归：")
src = open(os.path.join(BASE, "app", "pipeline.py"), encoding="utf-8").read()
check("已定义 keep_for_section()", "def keep_for_section(" in src)
check("裁剪按板块调用（trim_section(section, keep)）",
      bool(re.search(r"db\.trim_section\(section,\s*keep\)", src)))
check("已删除旧的全局单值写法",
      'keep = int(config.get("per_section_keep"' not in src)

# 配置模板也要同步，否则新克隆会缺这一项
example = os.path.join(BASE, "config.example.yaml")
ex_txt = open(example, encoding="utf-8").read() if os.path.isfile(example) else ""
check("config.example.yaml 已同步 per_section_keep_override",
      "per_section_keep_override" in ex_txt and "国内新闻: 500" in ex_txt)

print()
print(f"合计 {total} 项，失败 {failed} 项。")
sys.exit(1 if failed else 0)
