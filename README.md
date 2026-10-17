# Gamepad Haptic / Force-Feedback / Adaptive-Trigger Research

> 手柄力反馈 · 自适应扳机 · 触觉震动 —— 综合研究与工程实现
> A consolidated research + engineering repo for gamepad force-feedback, adaptive triggers and haptic feedback.

本仓库合并了三部分工作：跨厂商协议方法论、触觉/扳机研究工程、音频转震动中间层。
This repo consolidates three tracks: cross-vendor protocol methodology, haptics/trigger engineering, and an audio-to-vibration middle layer.

## 目录结构 / Repository Layout

| 路径 / Path | 内容 / Content |
|---|---|
| `docs/` | 协议方法论与跨厂商结构综述（5 篇）/ protocol methodology & cross-vendor overview |
| `tools/bitpack_offset_calc.py` | 位域打包偏移计算器 / bit-packing offset calculator |
| `haptics-research/` | 触觉与扳机研究工程：DS 协议翻译、虚拟 DualSense、抓帧与分析脚本、findings |
| `haptic-assistant/` | 音频转震动中间层（震动小助手）：音频直驱震动 + 扳机动作对齐 |

### `docs/` — 协议方法论 / Protocol Methodology

- `01-术语与代号表.md` — 术语与代号 / glossary
- `02-方法论-静态逆向手柄配置协议.md` — 不跑程序也能还原配置字段偏移 / static offset recovery
- `03-自适应扳机协议综述.md` — 阻尼/振动/射击/锁定/常规 的通用建模 / semantic modeling
- `04-厂商甲-网页驱动HID协议.md` — 网页驱动 HID 帧结构 / WebHID frame format
- `05-厂商乙-力反馈扳机协议.md` — 720B 配置 blob 与扳机三元组偏移 / blob layout & offsets

## 核心结论 / Key Takeaways

- **语义统一建模 / Unified semantics**：阻尼、振动、射击、锁定、常规五类扳机语义可跨厂商映射；中间层只认语义，输出时查厂商表。
- **纯静态偏移还原 / Static offset recovery**：复刻 UI 侧位域打包器，零硬件即可算出配置字段在 blob 里的字节偏移，并与厂商自声明长度交叉验证。
- **音频→震动实时中间层 / Real-time audio-to-haptics**：onset + 不应期策略，左右马达差异化输出，显著提升手感一致性。

## 说明 / Notes

- 内容用于研究与教育目的 / for research and education.
- 不含任何第三方闭源程序的二进制、源码或字符串转储 / no third-party closed-source binaries or dumps.
