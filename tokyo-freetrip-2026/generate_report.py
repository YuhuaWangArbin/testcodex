#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 results/ 下的调研JSON汇总为 report.md。

- 读取 fields.yaml 获取字段分类与顺序
- 读取 outline.yaml 获取 topic、output_dir、items 顺序、行程背景
- 覆盖每个item的所有字段；跳过含[不确定]、在uncertain数组中、或为空的字段
- 目录显示：序号、名称（锚点）、用户选择的摘要字段
"""

import json
import re
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent
FIELDS_PATH = BASE / "fields.yaml"
OUTLINE_PATH = BASE / "outline.yaml"

# 目录中显示的摘要字段（用户选择）
SUMMARY_FIELDS = ["best_day_fit", "suggested_duration", "proximity_to_disney_area"]
SUMMARY_LABELS = {
    "best_day_fit": "适合",
    "suggested_duration": "时长",
    "proximity_to_disney_area": "就近度",
}

# category 多语言映射（中中/中英双向）
CATEGORY_MAPPING = {
    "基本信息": ["basic_info", "基本信息"],
    "交通": ["transport", "access", "交通"],
    "亮点与体验": ["highlights_experience", "亮点与体验"],
    "实用信息": ["practical_info", "实用信息"],
    "行程适配": ["itinerary_fit", "行程适配"],
}
_SKIP_KEYS = {"_source_file", "uncertain"}
_NESTED_KEYS = {k for keys in CATEGORY_MAPPING.values() for k in keys}


def slugify(name):
    """生成markdown锚点用的slug。"""
    s = name.lower().strip()
    s = re.sub(r"[（(].*?[)）]", "", s)  # 去掉括号内容
    s = re.sub(r"[\s·・/、,，。.]+", "-", s.strip())
    s = re.sub(r"[^\w一-鿿-]", "", s)
    return s.strip("-")


def load_fields():
    with FIELDS_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    categories = []  # [(category_name, [(field_name, description), ...]), ...]
    field_desc = {}
    for cat in data.get("field_categories", []):
        fields = []
        for fld in cat.get("fields", []):
            fields.append(fld["name"])
            field_desc[fld["name"]] = fld.get("description", "")
        categories.append((cat["category"], fields))
    return categories, field_desc


def load_outline():
    with OUTLINE_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    topic = data.get("topic", "调研报告")
    output_dir = data.get("execution", {}).get("output_dir", "./results")
    item_order = [it["name"] for it in data.get("items", [])]
    trip = data.get("trip_context", {})
    return topic, output_dir, item_order, trip


def get_field(data, field_name):
    """扁平优先，其次嵌套dict中查找。"""
    if field_name in data:
        return data[field_name]
    for k, v in data.items():
        if k in _NESTED_KEYS and isinstance(v, dict) and field_name in v:
            return v[field_name]
    return None


def is_uncertain(value, field_name, uncertain_list):
    if field_name in uncertain_list:
        return True
    if value is None:
        return True
    if isinstance(value, str) and (not value.strip() or "[不确定]" in value):
        return True
    return False


def format_value(value):
    if isinstance(value, list):
        if all(isinstance(x, dict) for x in value):
            return "\n".join("- " + " | ".join(f"{k}: {v}" for k, v in d.items()) for d in value)
        return "、".join(str(x) for x in value)
    if isinstance(value, dict):
        return "；".join(f"{k}: {v}" for k, v in value.items())
    text = str(value)
    return text


def short(value, limit=40):
    """目录摘要用：截断长文本，取第一句/前若干字。"""
    if value is None:
        return "—"
    text = str(value).split("。")[0].split("[不确定")[0].strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > limit:
        text = text[:limit] + "…"
    return text or "—"


def load_results(output_dir, item_order):
    results_dir = (BASE / Path(output_dir).name) if not Path(output_dir).is_absolute() else Path(output_dir)
    if not results_dir.exists():
        results_dir = BASE / "results"
    records = []
    for jf in results_dir.glob("*.json"):
        with jf.open(encoding="utf-8") as f:
            records.append(json.load(f))

    def order_key(rec):
        name = rec.get("name", "")
        for i, item in enumerate(item_order):
            key = item.split("（")[0].split("(")[0][:4]
            if key and key in name:
                return i
        return len(item_order)

    records.sort(key=order_key)
    return records


def build_report(topic, trip, categories, field_desc, records):
    out = []
    out.append(f"# {topic}\n")

    # 行程背景
    if trip:
        out.append("## ✈️ 行程背景\n")
        out.append(f"- **日期**：{trip.get('dates', '')}")
        out.append(f"- **进出机场**：{trip.get('airport_in_out', '')}")
        out.append(f"- **基地**：{trip.get('base_city', '')}")
        out.append(f"- **季节**：{trip.get('season', '')}")
        fixed = trip.get("fixed_schedule", [])
        if fixed:
            sched = "；".join(f"{s['date']} {s['plan']}" for s in fixed)
            out.append(f"- **已定行程**：{sched}")
        days = trip.get("days_to_plan", [])
        if days:
            out.append(f"- **待规划日**：{', '.join(str(d) for d in days)}")
        prefs = trip.get("preferences", [])
        if prefs:
            out.append(f"- **玩法偏好**：{', '.join(prefs)}")
        out.append("")

    # 目录
    out.append("## 📑 目录\n")
    for i, rec in enumerate(records, 1):
        name = rec.get("name", "未命名")
        anchor = slugify(name)
        parts = []
        for sf in SUMMARY_FIELDS:
            val = get_field(rec, sf)
            if val is not None:
                parts.append(f"{SUMMARY_LABELS.get(sf, sf)}: {short(val)}")
        summary = " ｜ ".join(parts)
        line = f"{i}. [{name}](#{anchor})"
        if summary:
            line += f"<br>　{summary}"
        out.append(line)
    out.append("")

    # 详细内容
    out.append("## 📋 详细内容\n")
    for i, rec in enumerate(records, 1):
        name = rec.get("name", "未命名")
        anchor = slugify(name)
        uncertain_list = rec.get("uncertain", []) or []
        out.append(f'<a id="{anchor}"></a>')
        out.append(f"### {i}. {name}\n")

        used = set(_SKIP_KEYS) | _NESTED_KEYS
        for cat_name, field_names in categories:
            rows = []
            for fn in field_names:
                used.add(fn)
                val = get_field(rec, fn)
                if is_uncertain(val, fn, uncertain_list):
                    continue
                rows.append((field_desc.get(fn, fn), format_value(val)))
            if rows:
                out.append(f"**{cat_name}**\n")
                for label, val in rows:
                    if "\n" in val or len(val) > 100:
                        out.append(f"- *{label}*：")
                        for ln in val.split("\n"):
                            out.append(f"  > {ln}")
                    else:
                        out.append(f"- *{label}*：{val}")
                out.append("")

        # 其他信息（未在fields定义的额外字段）
        extras = []
        for k, v in rec.items():
            if k in used:
                continue
            extras.append((k, v))
        if extras:
            out.append("**其他信息**\n")
            for k, v in extras:
                out.append(f"- *{k}*：{format_value(v)}")
            out.append("")

        # 待核实字段
        if uncertain_list:
            out.append("**⚠️ 待出行前核实（以官网为准）**\n")
            for fn in uncertain_list:
                out.append(f"- {field_desc.get(fn, fn)}（`{fn}`）")
            out.append("")

        out.append("---\n")

    return "\n".join(out)


def main():
    categories, field_desc = load_fields()
    topic, output_dir, item_order, trip = load_outline()
    records = load_results(output_dir, item_order)
    report = build_report(topic, trip, categories, field_desc, records)
    report_path = BASE / "report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"已生成报告: {report_path}")
    print(f"共 {len(records)} 个item")


if __name__ == "__main__":
    main()
