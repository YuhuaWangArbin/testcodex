#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 results/*.json 汇总为 report.md。
目录摘要字段：unit_price_range（参考单价）、warranty_terms（质保）。
跳过 [不确定] 值与 uncertain 数组中列出的字段。
"""
import json
import glob
import os
import re

import yaml

BASE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE, "results")
FIELDS_PATH = os.path.join(BASE, "fields.yaml")
OUTLINE_PATH = os.path.join(BASE, "outline.yaml")
REPORT_PATH = os.path.join(BASE, "report.md")

# 目录中展示的摘要字段
SUMMARY_FIELDS = [
    ("unit_price_range", "参考单价"),
    ("warranty_terms", "质保"),
]
SUMMARY_TRUNC = 50  # 摘要字段截断长度

# category 名 -> 可能的 JSON key（双向映射，兼容中英/嵌套）
CATEGORY_MAPPING = {
    "基本信息": ["basic_info", "基本信息"],
    "老房适配性（含越秀/岭南本地化）": ["oldhouse_fit", "老房适配性（含越秀/岭南本地化）", "老房适配性"],
    "资质与合规": ["qualification_compliance", "资质与合规"],
    "报价与预算（重点）": ["price_budget", "报价与预算（重点）", "报价与预算"],
    "口碑与质量保障（重点）": ["reputation_quality", "口碑与质量保障（重点）", "口碑与质量保障"],
    "风险点": ["risks", "风险点"],
}

INTERNAL_KEYS = {"_source_file", "uncertain"}
NESTED_TOPLEVEL = set(sum(CATEGORY_MAPPING.values(), []))


def load_fields():
    data = yaml.safe_load(open(FIELDS_PATH, encoding="utf-8"))
    cats = []
    for cat in data.get("field_categories", []):
        name = cat["category"]
        fields = [(f["name"], f.get("description", "")) for f in cat.get("fields", [])]
        cats.append((name, fields))
    return cats


def find_value(obj, field_name, category=None):
    """字段查找顺序：顶层 -> category映射key -> 遍历所有嵌套dict。"""
    if field_name in obj and not isinstance(obj[field_name], dict):
        return obj[field_name]
    # category 映射 key
    if category:
        for key in CATEGORY_MAPPING.get(category, []):
            sub = obj.get(key)
            if isinstance(sub, dict) and field_name in sub:
                return sub[field_name]
    # 遍历所有嵌套 dict
    for v in obj.values():
        if isinstance(v, dict) and field_name in v:
            return v[field_name]
    return None


def is_uncertain(value, field_name, uncertain_list):
    if value is None:
        return True
    if isinstance(value, str) and (value.strip() == "" or "[不确定]" in value):
        return True
    if field_name in uncertain_list:
        return True
    return False


def format_value(value):
    """格式化复杂值。"""
    if isinstance(value, list):
        if all(isinstance(x, dict) for x in value) and value:
            lines = []
            for d in value:
                lines.append(" | ".join(f"{k}: {v}" for k, v in d.items()))
            return "\n" + "\n".join(f"  - {ln}" for ln in lines)
        if len(value) > 4 or any(len(str(x)) > 30 for x in value):
            return "\n" + "\n".join(f"  - {x}" for x in value)
        return "、".join(str(x) for x in value)
    if isinstance(value, dict):
        return "; ".join(f"{k}: {v}" for k, v in value.items())
    text = str(value)
    if len(text) > 100:
        # 长文本用 blockquote 提升可读性
        return "\n\n  > " + text.replace("\n", "\n  > ")
    return text


def slug_anchor(name):
    """生成 markdown 锚点（GitHub 风格：小写、空格转-、移除部分符号）。"""
    s = name.lower()
    s = re.sub(r"[（）()/\\、，,。.：:；;\"'\[\]【】]", "", s)
    s = s.replace(" ", "-")
    return s


def truncate(text, n):
    text = str(text).replace("\n", " ").strip()
    return text if len(text) <= n else text[:n] + "…"


def main():
    outline = yaml.safe_load(open(OUTLINE_PATH, encoding="utf-8"))
    topic = outline.get("topic", "调研报告")
    item_order = [i["name"] for i in outline.get("items", [])]

    categories = load_fields()
    field_desc = {}
    for _, fields in categories:
        for fn, fd in fields:
            field_desc[fn] = fd

    # 读取所有 JSON
    docs = {}
    for f in sorted(glob.glob(os.path.join(RESULTS_DIR, "*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        docs[d.get("name", os.path.basename(f))] = d

    # 按 outline 顺序排列
    ordered_names = [n for n in item_order if n in docs] + [n for n in docs if n not in item_order]

    out = []
    out.append(f"# {topic} — 调研报告\n")
    out.append(f"> 共 {len(ordered_names)} 个调研对象。标注[不确定]的字段已跳过，需实地核验。\n")

    # ===== 目录 =====
    out.append("## 目录\n")
    for idx, name in enumerate(ordered_names, 1):
        d = docs[name]
        anchor = slug_anchor(name)
        parts = []
        for fkey, flabel in SUMMARY_FIELDS:
            val = find_value(d, fkey)
            uncertain_list = d.get("uncertain", [])
            if is_uncertain(val, fkey, uncertain_list):
                parts.append(f"{flabel}: [待核验]")
            else:
                parts.append(f"{flabel}: {truncate(val, SUMMARY_TRUNC)}")
        summary = " ｜ ".join(parts)
        out.append(f"{idx}. [{name}](#{anchor}) — {summary}")
    out.append("")

    # ===== 详细内容 =====
    out.append("\n---\n")
    for idx, name in enumerate(ordered_names, 1):
        d = docs[name]
        uncertain_list = d.get("uncertain", [])
        out.append(f"\n## {idx}. {name}\n")

        # 基础元信息
        if d.get("category"):
            out.append(f"**类别**：{d['category']}\n")

        used_fields = set(["name", "id", "category"])
        for cat_name, fields in categories:
            rows = []
            for fname, _ in fields:
                used_fields.add(fname)
                val = find_value(d, fname, cat_name)
                if is_uncertain(val, fname, uncertain_list):
                    continue
                rows.append((fname, val))
            if rows:
                out.append(f"### {cat_name}\n")
                for fname, val in rows:
                    label = field_desc.get(fname, fname)
                    label_short = label.split("：")[0].split("【")[0].strip()[:18] if label else fname
                    out.append(f"- **{fname}**（{label_short}）：{format_value(val)}")
                out.append("")

        # 其他信息（JSON有但fields未定义）
        extras = []
        for k, v in d.items():
            if k in INTERNAL_KEYS or k in NESTED_TOPLEVEL or k in used_fields:
                continue
            if isinstance(v, dict):
                continue
            if is_uncertain(v, k, []):
                continue
            extras.append((k, v))
        if extras:
            out.append("### 其他信息\n")
            for k, v in extras:
                out.append(f"- **{k}**：{format_value(v)}")
            out.append("")

        # 不确定字段清单（逐行显示）
        if uncertain_list:
            out.append("### ⚠️ 待核验字段（不确定）\n")
            for uf in uncertain_list:
                out.append(f"- {uf}")
            out.append("")

    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    print(f"报告已生成: {REPORT_PATH}")
    print(f"调研对象: {len(ordered_names)} 个")


if __name__ == "__main__":
    main()
