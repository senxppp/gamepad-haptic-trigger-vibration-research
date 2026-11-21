# Gamepad Haptic / Force-Feedback / Adaptive-Trigger Research

手柄力反馈、自适应扳机与触觉震动的协议研究档案，外加一代已停止维护的实现。
A research archive for gamepad force-feedback, adaptive triggers and haptics, plus one retired implementation.

## 这个仓库是什么

三个阶段的工作堆在一起，定位不同、状态也不同。**先看这张表再决定读哪部分**：

| 目录 | 是什么 | 还有效吗 |
|---|---|---|
| `docs/` | 跨厂商协议方法论，5 篇 | **持续有效**。这是后续所有实现的来源，建议从这里读 |
| `haptics-research/` | 2026-09 的一轮真机研究：私有协议破解、扳机手感调色板、虚拟 DualSense 管线 | 结论有效，代码是当时的一次性验证脚本 |
| `haptic-assistant/` | 第一代「震动小助手」完整实现（自建音频分析 → 直发马达） | **已停止维护**，留作参考；接替者是 `apex-haptic-bridge` |
| `tools/` | 零散的位域计算小工具 | 按需取用 |

新项目在这里：**[apex-haptic-bridge](https://github.com/senxppp/apex-haptic-bridge)** —— USB/IP 虚拟设备 + 截官方引擎的包络流，
重写扳机渲染，带写入节流 / 停帧自愈 / 热插拔守护 / 222 条离线回归。

两代的分工差别在**谁来解析音频**：第一代自建回环抓取与特征提取、全链路自己扛；
第二代把解析交给厂商引擎，只负责设备间翻译和稳定性。

## `docs/` — 协议方法论

这 5 篇与具体硬件型号无关，是读其他部分的前提：

| 文件 | 内容 |
|---|---|
| `01-术语与代号表.md` | 术语与代号表 |
| `02-方法论-静态逆向手柄配置协议.md` | 不跑程序也能还原配置字段偏移 |
| `03-自适应扳机协议综述.md` | 阻尼 / 振动 / 射击 / 锁定 / 常规 的通用建模 |
| `04-厂商甲-网页驱动HID协议.md` | 网页驱动 HID 帧结构 |
| `05-厂商乙-力反馈扳机协议.md` | 720B 配置 blob 与扳机三元组偏移 |

三条跨厂商的结论：

- **语义可以统一建模**：阻尼、振动、射击、锁定、常规五类扳机语义可跨厂商映射；
  中间层只认语义，输出时查厂商表。
- **偏移可以纯静态还原**：复刻 UI 侧的位域打包器，零硬件即可算出配置字段在 blob 里的字节偏移，
  再与厂商自声明长度交叉验证。
- **音频转触觉要按 onset + 不应期做**：左右马达差异化输出，手感一致性明显好于等响度直映。

## `haptics-research/` — 2026-09 一轮真机研究

结论都在 `haptics-research/FINDINGS.md` 和 `docs/ApexSenseBridge-逆向与k5触觉桥接.md` 里，
后者是对开源桥接器 [ReynArts/ApexSenseBridge](https://github.com/ReynArts/ApexSenseBridge) 的独立逆向笔记，
与自研结论互相验证。

代码部分是一次性验证脚本，能跑但不再维护：

```
ds_bridge_daemon.py          虚拟 DS 宿主 + 输入喂入 + 震动/扳机翻译（当时的入口）
vib_out/flydigi_vib.py       握把震动驱动（私有协议 0xFFA0 直发）
vib_out/flydigi_trigger.py   扳机驱动 + 九种标定手感（feel() 接口）
vib_out/xinput_out.py        XInput 标准输出层
vib_out/pwm.py               PWM 细腻模式调制器
wanwei_k5_bridge.py          第三方视觉扳机工具的旁路桥
research/                    阶段验证脚本（抓帧、位图、管线演示、探针）
```

> ⚠️ 与 `haptic-assistant/vib_out/flydigi_vib.py` 存在职责重叠：两份都直发 `0xFFA0`。
> 前者是研究期的精简版（只够验证协议），后者是产品化的完整版（带重连与配置）。
> 如果要复用，取 `haptic-assistant/` 那份。

## `haptic-assistant/` — 第一代实现（已停止维护）

自建音频分析的全链路：WASAPI 回环 → 特征提取 → 映射 → 直发马达/扳机。
保留原因：它把「自己解析音频」这条路走完了，`src/analysis/features.py`、`src/mapping/mapper.py`
以及 `tools/` 下的标定脚本对理解触觉参数仍有参考价值。

`tools/` 里那些 `trigger_grip2.py` ~ `trigger_grip7.py`、`_dig_*.py`、`*.csv` 是当时的迭代残留，
按文件名序号能看出排查顺序，**不必逐个读**。

## 说明

- 内容用于研究与教育目的。不含任何第三方闭源程序的二进制、源码或字符串转储。
- 设备标识符、帧布局、模式语义均为互操作性观察结果，与厂商无隶属或背书关系。
