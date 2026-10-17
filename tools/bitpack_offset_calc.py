#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
位域打包偏移计算器（通用、自包含）

用途
----
很多手柄/外设的配置程序，会用一个「配置对象」描述每个字段占多少 bit，
再通过位域打包函数把它压成一个连续的字节缓冲区（配置 blob）。只要复刻这个
打包逻辑，就能在**不运行任何闭源程序、不需要硬件**的前提下，算出每个字段在
blob 里的绝对字节偏移。

本脚本是该方法的最小可运行演示：
  * 内置一个「合成示例 schema」（不代表任何真实产品），
  * 复刻位域打包（convProfilePos）逻辑，
  * 输出每个字段的 [字节偏移, 字节数, 位偏移, 位宽]。

也可以把自己的 schema 写成 JSON 传入：  python bitpack_offset_calc.py schema.json
JSON 约定：
  * 叶子是整数 = 该字段的 bit 宽
  * 对象 = 嵌套结构
  * {"__arr__": N, "of": <node>} = 长度为 N 的数组，元素为 of

运行
----
  python bitpack_offset_calc.py            # 用内置示例
  python bitpack_offset_calc.py my.json   # 用自己的 schema
"""

import sys
import json


# ---------------------------------------------------------------------------
# 内置合成示例 schema（演示：左右扳机各一份连续三元组 + 参数族）
# 注意：这是「教学用」的合成结构，字节偏移数字没有真实产品含义。
# ---------------------------------------------------------------------------
EXAMPLE_SCHEMA = {
    "global": {
        "enabled": 1,
        "reserve": 7,
    },
    "triggers": {
        "__arr__": 2,                      # 左右扳机各一份
        "of": {
            "mode": 8,                      # 模式
            "type": 8,                      # 类型（阻尼/振动/射击）
            "preset_id": 8,                 # 预设 id
            "follow_grip": 1,               # 跟随握把
            "reserve1": 7,
            "race_param": {                  # 阻尼族
                "__arr__": 4,
                "of": {"start": 8, "strength": 8},
            },
            "shot_param": {                  # 射击族
                "__arr__": 4,
                "of": {"break_pos": 8, "resist": 8, "travel": 8, "out_on": 8},
            },
        },
    },
    "travel": {
        "__arr__": 2,
        "of": {
            "start": 8, "end": 8, "valid_start": 8, "valid_end": 8,
        },
    },
}


# ---------------------------------------------------------------------------
# 复刻位域打包（convProfilePos）
# ---------------------------------------------------------------------------
class Cursor:
    __slots__ = ("pos",)
    def __init__(self):
        self.pos = 0


def walk(node, prefix, cur, out):
    """递归遍历 schema，计算每个叶子字段的 [binpos, binsize, bitoff, bitsize]。"""
    if isinstance(node, dict):
        if "__arr__" in node:
            n = node["__arr__"]
            child = node["of"]
            for i in range(n):
                walk(child, f"{prefix}[{i}]", cur, out)
            return
        for k, v in node.items():
            walk(v, f"{prefix}.{k}" if prefix else k, cur, out)
    else:
        bitsize = int(node)
        binpos = cur.pos // 8
        bitoff = cur.pos % 8
        binsize = (bitsize + bitoff + 7) // 8
        out[prefix] = [binpos, binsize, bitoff, bitsize]
        cur.pos += bitsize


def compute_offsets(schema):
    cur = Cursor()
    out = {}
    walk(schema, "", cur, out)
    return out, cur.pos


def print_offsets(out, total_bits):
    print(f"总位宽: {total_bits} bit  ->  { (total_bits + 7) // 8 } 字节\n")
    print(f"{'字段路径':42s} {'字节':>5s} {'位宽':>5s} {'位偏移':>6s}")
    print("-" * 64)
    for k, v in out.items():
        print(f"{k:42s} {v[0]:5d} {v[3]:5d} {v[2]:6d}")


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            schema = json.load(f)
        label = sys.argv[1]
    else:
        schema = EXAMPLE_SCHEMA
        label = "内置合成示例"
    print(f"=== 位域打包偏移计算（schema 来源: {label}）===\n")
    out, total = compute_offsets(schema)
    print_offsets(out, total)


if __name__ == "__main__":
    main()
