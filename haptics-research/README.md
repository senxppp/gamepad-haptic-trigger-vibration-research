# Flydigi APEX5 (八爪鱼5) 触觉研究 —— 让 85 吃下 DS 世界

把飞智八爪鱼5 变成能吃下 DualSense 生态的全功能手柄：DS 音频触觉、DS 扳机效果、
万维视觉扳机、XInput 游戏 —— 全部翻译到 85 的转子握把 + 力反馈扳机上。

> 研究周期：2026-09-25 ~ 09-27。全部结论真机实测验证（APEX5, VID_37D7 PID_2501, 蓝牙/USB）。
> 私有研究仓库，勿公开（含未发布逆向成果）。

## 核心成果一览

| 成果 | 状态 |
|---|---|
| 握把震动私有协议（0xFFA0, 32B 帧） | ✅ 破解+验证 |
| 力反馈扳机协议（0x51/0x52, 六种效果） | ✅ 破解+验证 |
| 感觉调色板（9 种标定手感） | ✅ 已封装 `feel()` |
| XInput 兼容（标准手柄通用路线） | ✅ 已发布 |
| PWM 细腻模式（转子马达手感增强） | ✅ 已发布 |
| 万维视觉扳机 → 85 直通（UDP 7878） | ✅ 破解+验证 |
| 虚拟 DualSense（usbip-win2 + libVIIPER） | ✅ 阶段1验证 |
| 音频触觉管线（触觉音频→虚拟DS→拦截→85） | ✅ 全链路验证 |
| 游戏原声 → 扳机感觉合成 | ✅ 全链路验证 |
| DS 原生 0x31 输出报文 | 🔒 虚拟设备只收 0x02（格式部分破解），待续 |

## 快速使用

```bash
# 全功能守护进程（虚拟DS + 输入喂入 + 震动/扳机翻译 + 音频触觉拦截）
python research/ds_bridge_daemon.py [运行秒数]

# 扳机感觉调色板演示（9 种标定手感）
python vib_out/flydigi_trigger.py demo

# 代码调用
from flydigi_trigger import FlydigiTrigger
trg = FlydigiTrigger(); trg.open()
trg.feel("机枪连发")                    # 或 强刹车拉弓/单发后座/持续嗡震...
trg.feel("强刹车拉弓", side=2, resistance=150)

from flydigi_vib import FlydigiVibration
vib = FlydigiVibration(); vib.open(); vib.set(200, 200)
```

前置：`pip install hidapi`；手柄连接；**游戏/工具测试触觉音频时把输出选到
"DualSense Wireless Controller" 扬声器**（虚拟 DS 由守护进程创建）。



## APEXtoDS 基础

部分研究基于社区工具 APEXtoDS（八爪鱼6 专用 DS→扳机翻译，作者另案发布）。
改造细节不在此公开；本仓库只含自研工具与协议研究。

## 文档索引

- [FINDINGS.md](FINDINGS.md) —— 全部逆向结论：协议字节、标定数据、架构分析、踩坑记录
- docs/ —— EF 帧布局逆向、项目总览等研究文档

## 目录

```
ds_bridge_daemon.py          全功能守护进程（日常使用入口）
vib_out/flydigi_vib.py       握把震动驱动（私有协议直发）
vib_out/flydigi_trigger.py   扳机驱动 + 感觉调色板（feel() 接口）
vib_out/xinput_out.py        XInput 标准输出层（其他品牌手柄）
vib_out/pwm.py               PWM 细腻模式调制器
wanwei_k5_bridge.py          万维视觉扳机→85 备胎桥（无空间站机器用）
research/                    阶段验证脚本（虚拟DS宿主/管线演示/0x02探针）
```

## 2026-10-11 增量：ApexSenseBridge 逆向 + k5 触觉桥接完整协议

- `docs/ApexSenseBridge-逆向与k5触觉桥接.md` —— 开源桥接器 [ReynArts/ApexSenseBridge](https://github.com/ReynArts/ApexSenseBridge) v1.0.1 的完整逆向笔记（输入合成策略 / DS 0x31 效果块→k5 六模式翻译表 / FORCEADAPT 帧格式 / VIIPER 反馈帧 / 调度防坑），与自研逆向互相验证零冲突
- k5 EF 输入帧布局（源码级校正版）：摇杆 4×i16LE@4、按键 primary@12 / secondary@13、PS@15.bit3、LT/RT@16/17、陀螺仪/加速度 i16LE@18-29（4096/g）
- APEX6 协议补充：0x57 RealtimeMotor = 马达 PCM 采样帧（8×{trigger,L,R}，0x80=零点）→ k5 握把触觉可由采样包络直出（0x12），无需回调钩
- `tools/`：probe_transport.py（0x10/0x11 输入传输状态探针）、hidhide_wl.py（HidHide 白名单 IOCTL 管理）、patch_apex5_parse.py（修复 ASB v1.0.1 对 k5 dongle 0x10 应答的误判，2 字节，已实测）
- 闭源第三方方案（APEXtoDS）的技术验证结论不在此仓库公开
