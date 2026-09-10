# -*- coding: utf-8 -*-
"""英文点词解释：词典聚合 + 缓存 + LLM 预留分支。

数据源（全部免费、短超时、失败降级）：
- dictionaryapi.dev：音标、词性、英英释义、例句
- MyMemory：中文释义（匿名有日限额，靠缓存省量）
- Wiktionary REST：补充释义
若 config.yaml 的 llm.api_key 非空，则优先走 OpenAI 兼容接口生成更丰富的解释，
失败时回落到词典聚合结果。
"""
import json
import logging
import os
import re

import requests

from . import db

log = logging.getLogger("worddict")

TIMEOUT = 5
_BASE = os.path.dirname(os.path.abspath(__file__))
IDIOMS_PATH = os.path.join(_BASE, "data", "idioms.json")

_idioms = None


def load_idioms():
    """加载内置习语/俚语/词组清单（懒加载，进程内缓存）。"""
    global _idioms
    if _idioms is None:
        try:
            with open(IDIOMS_PATH, "r", encoding="utf-8") as f:
                _idioms = json.load(f)
        except Exception as e:
            log.warning("加载 idioms.json 失败: %s", e)
            _idioms = []
    return _idioms


def _norm_word(word):
    w = re.sub(r"[^a-zA-Z'\-]", "", word or "").strip("'-").lower()
    return w


def _strip_html(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", " ", s).strip()


# ---------- 各数据源 ----------

def _from_dictionaryapi(w):
    """音标、词性、英英释义、例句。"""
    phonetic, senses = None, []
    try:
        r = requests.get(
            f"https://api.dictionaryapi.dev/api/v2/entries/en/{w}",
            timeout=TIMEOUT)
        if r.status_code != 200:
            return None, []
        entries = r.json()
    except Exception as e:
        log.info("dictionaryapi 查询失败 %s: %s", w, e)
        return None, []
    for entry in entries:
        if not phonetic:
            phonetic = entry.get("phonetic") or next(
                (p.get("text") for p in entry.get("phonetics", [])
                 if p.get("text")), None)
        for m in entry.get("meanings", []):
            pos = m.get("partOfSpeech", "")
            for d in m.get("definitions", [])[:2]:
                if d.get("definition"):
                    senses.append({
                        "pos": pos,
                        "definition_en": d["definition"],
                        "definition_zh": "",
                        "example": d.get("example", ""),
                    })
    return phonetic, senses[:6]


def _from_mymemory(w):
    """中文释义；失败返回 None。"""
    try:
        r = requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": w, "langpair": "en|zh-CN"},
            timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        text = ((r.json().get("responseData") or {}).get("translatedText") or "").strip()
        if not text or "MYMEMORY WARNING" in text.upper():
            return None
        if text.lower() == w.lower():
            return None
        return text
    except Exception as e:
        log.info("MyMemory 查询失败 %s: %s", w, e)
        return None


def _from_wiktionary(w):
    """补充释义；失败返回空列表。"""
    senses = []
    try:
        r = requests.get(
            f"https://en.wiktionary.org/api/rest_v1/page/definition/{w}",
            timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception as e:
        log.info("Wiktionary 查询失败 %s: %s", w, e)
        return []
    for _lang, entries in (data or {}).items():
        for entry in entries or []:
            pos = entry.get("partOfSpeech", "")
            for d in entry.get("definitions", [])[:2]:
                definition = _strip_html(d.get("definition", ""))
                if definition:
                    senses.append({
                        "pos": pos,
                        "definition_en": definition,
                        "definition_zh": "",
                        "example": "",
                    })
    return senses[:4]


def _related_phrases(w):
    """内置习语清单中包含该词的条目。"""
    out = []
    pat = re.compile(r"\b" + re.escape(w) + r"\b", re.I)
    for it in load_idioms():
        if pat.search(it.get("phrase", "")):
            out.append({
                "phrase": it["phrase"],
                "definition_zh": it.get("definition_zh", ""),
                "definition_en": it.get("definition_en", ""),
            })
        if len(out) >= 5:
            break
    return out


# ---------- LLM 预留分支 ----------

def _from_llm(w, llm_cfg):
    """调用 OpenAI 兼容 chat completions 生成解释。

    需要 config.yaml 中 llm.api_key 非空；base_url 为空时默认
    https://api.openai.com/v1。任何失败返回 None，由调用方回落到词典路径。
    """
    base_url = (llm_cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    model = llm_cfg.get("model") or "gpt-4o-mini"
    prompt = (
        "Explain the English word '%s' for a Chinese learner. "
        "Reply with ONLY a JSON object: "
        "{\"phonetic\": str, \"senses\": [{\"pos\": str, \"definition_en\": str, "
        "\"definition_zh\": str, \"example\": str}], \"etymology\": str, "
        "\"usage\": str (slang/allusion/usage notes, Chinese ok)}."
    ) % w
    try:
        r = requests.post(
            base_url + "/chat/completions",
            headers={"Authorization": "Bearer " + llm_cfg["api_key"],
                     "Content-Type": "application/json"},
            json={"model": model,
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.3},
            timeout=30)
        if r.status_code != 200:
            log.info("LLM 查询失败 %s: HTTP %s", w, r.status_code)
            return None
        content = (r.json()["choices"][0]["message"]["content"] or "").strip()
        content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.M).strip()
        data = json.loads(content)
        result = {
            "word": w,
            "phonetic": data.get("phonetic"),
            "senses": [{
                "pos": s.get("pos", ""),
                "definition_en": s.get("definition_en", ""),
                "definition_zh": s.get("definition_zh", ""),
                "example": s.get("example", ""),
            } for s in data.get("senses", []) if s.get("definition_en")],
            "etymology": data.get("etymology") or "",
            "usage": data.get("usage") or "",
            "translation_zh": "",
            "phrases": _related_phrases(w),
            "source": "llm",
        }
        return result if result["senses"] else None
    except Exception as e:
        log.info("LLM 查询异常 %s: %s", w, e)
        return None


# ---------- 主入口 ----------

def lookup_word(word, config=None):
    """查询单词解释。命中缓存直接返回；否则词典聚合或 LLM 生成并写入缓存。

    全部来源失败时返回 {"word", "ok": False, "message", "cached": False}，
    不抛异常、不写缓存（以便之后重试）。
    """
    w = _norm_word(word)
    if not w:
        return {"word": word or "", "ok": False,
                "message": "无效的单词", "cached": False}

    cached = db.get_word_cache(w)
    if cached:
        try:
            data = json.loads(cached)
            data["cached"] = True
            return data
        except Exception:
            pass

    # LLM 预留分支：api_key 非空时优先，失败回落词典
    llm_cfg = ((config or {}).get("llm") or {})
    if llm_cfg.get("api_key"):
        data = _from_llm(w, llm_cfg)
        if data:
            data["cached"] = False
            db.set_word_cache(w, json.dumps(data, ensure_ascii=False))
            return data

    phonetic, senses = _from_dictionaryapi(w)
    zh = _from_mymemory(w)
    if not senses:
        senses = _from_wiktionary(w)
    if zh:
        for s in senses:
            s["definition_zh"] = zh

    if not senses and not zh and not phonetic:
        return {"word": w, "ok": False,
                "message": "暂时无法获取该词释义（词典服务不可达），请稍后重试",
                "cached": False}

    data = {
        "word": w,
        "phonetic": phonetic or "",
        "senses": senses,
        "translation_zh": zh or "",
        "etymology": "",
        "phrases": _related_phrases(w),
        "source": "dictionary",
        "cached": False,
    }
    db.set_word_cache(w, json.dumps(data, ensure_ascii=False))
    return data
