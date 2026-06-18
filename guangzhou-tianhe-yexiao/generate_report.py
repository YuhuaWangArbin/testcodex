#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""读取 results/ 下所有调研 JSON，结合 fields.yaml 生成 markdown 汇总报告。
- 跳过含 [不确定] 的字段值
- 跳过 uncertain 数组中列出的字段
- 跳过空值
"""
import json
import re
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent
FIELDS_PATH = BASE / "fields.yaml"
RESULTS_DIR = BASE / "results"
REPORT_PATH = BASE / "report.md"

# 目录摘要字段（用户选择）
SUMMARY_FIELDS = ["avg_price", "cuisine", "area"]

SKIP_KEYS = {"_source_file", "uncertain"}

# category 名 -> JSON 可能的 key（双向兼容，本项目为扁平结构，主要用于查找回退）
CATEGORY_MAPPING = {
    "基本信息": ["basic_info", "基本信息"],
    "价格（重点）": ["price", "价格", "价格（重点）"],
    "营业时间": ["business_hours", "营业时间"],
    "菜品特色": ["dishes", "菜品特色"],
    "环境与场景": ["environment", "环境与场景"],
    "交通便利": ["transport", "交通便利"],
    "口碑评价": ["reputation", "口碑评价"],
}


def slugify(name):
    s = re.sub(r"[\s（）()·\.／/]+", "-", name.strip())
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def load_fields():
    with FIELDS_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    categories = []  # [(category_name, [(field_name, label), ...])]
    label_map = {}
    fc = data.get("field_categories", {})
    if isinstance(fc, dict):
        for cat, fields in fc.items():
            flist = []
            for fld in fields or []:
                name = fld["name"]
                label = fld.get("label", name)
                flist.append((name, label))
                label_map[name] = label
            categories.append((cat, flist))
    return categories, label_map


def find_value(data, field, category):
    """字段查找顺序：顶层 -> category 映射 key -> 遍历所有嵌套 dict"""
    if field in data:
        return data[field]
    for key in CATEGORY_MAPPING.get(category, []):
        sub = data.get(key)
        if isinstance(sub, dict) and field in sub:
            return sub[field]
    for v in data.values():
        if isinstance(v, dict) and field in v:
            return v[field]
    return None


def is_skippable(value, field, uncertain):
    if field in uncertain:
        return True
    if value is None or (isinstance(value, str) and not value.strip()):
        return True
    if isinstance(value, str) and "[不确定]" in value:
        return True
    return False


def format_value(value):
    if isinstance(value, list):
        if value and all(isinstance(x, dict) for x in value):
            return "<br>".join(" | ".join(f"{k}: {v}" for k, v in d.items()) for d in value)
        return "、".join(str(x) for x in value)
    if isinstance(value, dict):
        return "；".join(f"{k}: {v}" for k, v in value.items())
    text = str(value)
    if len(text) > 100:
        return text  # 详细内容已在表格外以列表呈现，长文本保留原样
    return text


def collect_extra(data, defined_fields):
    extra = {}
    for k, v in data.items():
        if k in SKIP_KEYS or k in defined_fields:
            continue
        if k in CATEGORY_MAPPING:  # 嵌套结构顶级 key
            continue
        extra[k] = v
    return extra


def main():
    categories, label_map = load_fields()
    defined_fields = {name for _, flist in categories for name, _ in flist}
    json_files = sorted(RESULTS_DIR.glob("*.json"))
    items = []
    for jf in json_files:
        with jf.open(encoding="utf-8") as f:
            items.append((jf, json.load(f)))

    lines = []
    topic_data = yaml.safe_load(FIELDS_PATH.read_text(encoding="utf-8"))
    topic = topic_data.get("topic", "调研报告")
    lines.append(f"# {topic} — 调研汇总报告\n")
    lines.append(f"> 共 {len(items)} 家店铺 | 含 [不确定] 及空值字段已跳过\n")

    # ---- 目录 ----
    lines.append("## 目录\n")
    for i, (_, data) in enumerate(items, 1):
        name = data.get("name", "未命名")
        anchor = slugify(name)
        summary_parts = []
        for sf in SUMMARY_FIELDS:
            val = data.get(sf)
            if val and "[不确定]" not in str(val):
                summary_parts.append(f"{label_map.get(sf, sf)}: {val}")
        summary = " | ".join(summary_parts)
        lines.append(f"{i}. [{name}](#{anchor}) — {summary}")
    lines.append("")

    # ---- 详细内容 ----
    lines.append("\n---\n")
    for i, (jf, data) in enumerate(items, 1):
        name = data.get("name", "未命名")
        anchor = slugify(name)
        uncertain = set(data.get("uncertain", []))
        lines.append(f'\n<a id="{anchor}"></a>\n')
        lines.append(f"## {i}. {name}\n")
        for cat, flist in categories:
            rows = []
            for field, label in flist:
                if field == "name":
                    continue
                val = find_value(data, field, cat)
                if is_skippable(val, field, uncertain):
                    continue
                rows.append(f"| {label} | {format_value(val)} |")
            if rows:
                lines.append(f"### {cat}\n")
                lines.append("| 字段 | 内容 |")
                lines.append("| --- | --- |")
                lines.extend(rows)
                lines.append("")
        # 其他信息
        extra = collect_extra(data, defined_fields)
        if extra:
            lines.append("### 其他信息\n")
            lines.append("| 字段 | 内容 |")
            lines.append("| --- | --- |")
            for k, v in extra.items():
                if is_skippable(v, k, uncertain):
                    continue
                lines.append(f"| {k} | {format_value(v)} |")
            lines.append("")
        # 不确定字段列表
        if uncertain:
            lines.append("### 待核实字段（不确定）\n")
            for u in data.get("uncertain", []):
                lines.append(f"- {label_map.get(u, u)}")
            lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"报告已生成: {REPORT_PATH} ({len(items)} 家店铺)")


if __name__ == "__main__":
    main()
