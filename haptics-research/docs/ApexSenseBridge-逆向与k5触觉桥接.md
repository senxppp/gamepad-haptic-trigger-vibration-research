# ApexSenseBridge 逆向笔记与 k5 触觉桥接协议大全

> 对象：[ReynArts/ApexSenseBridge](https://github.com/ReynArts/ApexSenseBridge) v1.0.1（开源 C++20，感谢作者的杰出工作）+ 飞智 APEX5/6 私有协议（自主逆向，实测验证）。
> 2026-09-25 → 2026-10-11 的研究成果汇总。本仓库不包含任何第三方闭源程序的内部细节。

# ApexSenseBridge v1.0.1 控制系统逆向笔记

> 来源：开源源码直读（`research/asb_src`，C++20，21628 行）+ 本机实测抓帧互证（2026-10-11）。
> 与我们自有逆向（`交接文档-APEXtoDS八爪鱼5改造`、感觉调色板）交叉验证，一致性极高。
> 价值：① 看懂现役方案 ② 给上游提 PR 的地图 ③ A 线工具可复用的帧级知识。

## 一、整体数据流

```
物理 k5 (VID 37D7 PID 2501)
  ├─ XInput 接口 ──────────── 板载配置映射的标准按键（官方枚举，真实来源）
  ├─ 0xFFA0 Col01 读(0x04 5A A5 EF ...) ── EF 操作员流（0x11 使能后 ~148Hz）
  └─ 0xFFA0 Col01 写(0x03 5A A5 ...) ── 0x51 扳机 / 0x12 震动 / 0xA1-A2 档位 / 0xA7-A9 RGB

libVIIPER v0.7.0-asb13（进程内虚拟 DS，usbip-win2 总线）← 游戏把虚拟 DS 当真 PS5 手柄
  游戏输出 → VIIPER 拆成 3 类反馈帧交给宿主：
    帧 0x01 = HID 输出（27-30B）
    帧 0x02 = 音频遥测（16B）
    帧 0x03 = 8ms 触觉波形（36-64B）

宿主三个翻译桥：
  AdaptiveTriggerBridge ─ 帧0x01 的扳机效果块 → 语义翻译 → 0x51 下发
  RumbleBridge          ─ 帧0x01 的 rumble + 帧0x02 遥测 → 混合 → 0x12 下发
  LightbarBridge        ─ 灯条 RGB → 0xA7/A8/A9 下发

输入合成（反向）：composeApex5InputState → SetDualSenseDeviceState 喂虚拟 DS
```

## 二、输入侧：EF 帧布局（0xEF 操作员数据，源码级，32B）

```
[4..5]  左摇杆X  i16LE      [6..7]  左摇杆Y
[8..9]  右摇杆X  i16LE      [10..11] 右摇杆Y
[12] 按键组1: bit0十字上 bit1右 bit2下 bit3左 bit4=A bit5=B bit6=Back bit7=X
[13] 按键组2: bit0=Y bit1=Start bit2=LB bit3=RB bit6=L3 bit7=R3
[15] bit3 = PS 键
[16] LT u8     [17] RT u8
[18..23] 陀螺仪 XYZ 各 i16LE
[24..29] 加速度 XYZ 各 i16LE（约 4096/g；×625/256 折算 DS 的 10000/g）
```

**与旧逆向互校**：我们标定的 A=[12].bit4、B=[12].bit5、L3=[13].bit6 全部正确 ✓。
（旧记录"[4..7]=摇杆 u8 中心128"实为 4×i16LE 误判；"[19..30] 陀螺"实际 [18..29]，对位偏 1。）

**合成策略（巧）**：`composeApex5InputState` 以 XInput 板载映射为基础，EF 流只补三样 XInput 给不了的：
① LT/RT **同时**按压（两者 EF 值均 >8 时才启用独立值，避免 XInput 合并轴丢信息）
② PS 键（[15].bit3）③ 陀螺仪/加速度/电量。→ 完全绕开了"逆向 k5 按键位表"这个 C 线死胡同。

## 三、输出侧：k5 命令帧（0xFFA0 Col01 写）

```
0x01  GetInfo（身份/电量/连接模式 raw）
0x10  读输入传输   k5 应答 [6..10] = c,r,k,m,校验和 ← [10] 是校验和不是开关（dongle 坑，已补丁）
0x11  设置输入传输 {c, r, k, m, t}，0xFF = 保持不变（我们已验证生效，EF 流即开）
0x12  握把震动     [4]=6 [5]=左 [6]=右（与我们逆向一致）
0x51  FORCEADAPT 扳机（kCmdSetForceTrigger=81=0x51，与我们逆向完全一致）：
      [4]=长度 [5]=apply(1下发/0释放) [6]=side(1左2右) [7]=mode [8..]=参数
      mode0 Normal:      {apply, side}
      mode1 Race 阻力:   {apply, side, 1, start, res(≥1), match}   ← start=0&&match 强制 match=0（官方 quirk）
      mode2 SniperBreak 段落: {apply, side, 2, start, length, strength, 0, match}
      mode3 RecoilRattle 后座颤: {apply, side, 3, start, p1, p2, freq, match}
      mode4 Lock:        {apply, side, 4, start, 255, match}       ← 强度恒 255（与我们逆向一致）
      mode5 Vibration:   同 mode3 形态（作者自注"文档不足"，UI 未暴露）
0xA1 档位查询 / 0xA2 应用档位（1-4 槽）
0xA7/0xA8/0xA9 RGB 读/写起/写包（12 颗 LED，380B 配置，20B/包）
```

对照感觉调色板：我们的 RACE[60,30/60/100] 等参数位置逐字节吻合；它的自动换算 peak×8（≤64）
恰好落在我们标定的"RACE 150 太强、30-100 舒适"区间——两套独立研究互证。

## 四、DS 0x31 效果块（11B）→ k5 翻译表（扳机手感的核心）

```
效果块: [0]=类型码 [1..2]=分区掩码(10bit) [3..6]=10×3bit 强度 [9]=频率
行程换算: zone(0..9) → stroke = zone×19.2（0..192）

0x21 持续阻力        → mode1 Race      {start=首区行程, res=峰值×8}
0x22/0x25 Weapon/自动 → mode2 段落      {start, length, (3bit值+1)×8}
0x23 Vibration 自动   → mode3 后座颤    {start, 1, 60, freq}
0x27 Bow 拉弓        → mode3 后座颤    {start, 1, 平均(两个3bit)×10, freq}
其他带频率            → mode3 后座颤    {从半峰值区起平均振幅, freq<10 时振幅减半}
掩码=0               → Normal 复位
```

## 五、调度与防坑（工程细节）

- **空效果块（[0]==0）跳过不释放**——COD 类游戏会交错发空块，释放会导致扳机振荡（v1.0.1 修复 #23/#38）
- 翻译失败（unsupported 类型）→ 计数 + 保留上次效果？不——v1.0.1 改为**释放扳机**防卡死
- 去重：与上次相同的效果不下发；写入失败 → failed 标志停止（无重试风暴）
- RumbleBridge：音频流 **100ms 超时清零**；标准震动 force 即时写（延迟敏感）
- 左右扳机共用一条写通道：都活跃时**交替路由**，效果相同则 Both 一次发
- 用户可调：扳机强度 0-100%、震动 0-200%（>100% 只增强 k5 握把电机；6 Pro 恒 100%）

## 六、VIIPER asb13 反馈帧字节级

```
帧0x01 (HID 输出): [0]enableBits1 [1]enableBits2 [2]rumbleR [3]rumbleL [4]enableBits3
                   [5..15] 右扳机效果块11B [16..26] 左扳机效果块11B [27..29] 灯条RGB(当 enableBits2&0x04)
                   ← 我们旧逆向 0x02 报文 byte[2]=rumbleSmall/byte[3]=rumbleLarge 完全对应 ✓
帧0x02 (音频遥测): [0..3]seq u32 [4..5]L-energy [6..7]R-energy [8..9]L-peak [10..11]R-peak [12..13]L-transient [14..15]R-transient
帧0x03 (8ms 波形): [0..3]seq u32 + 8×(L i16 + R i16)（48kHz→1kHz 低通抽取后的 1ms/采样）
                   ≥64B 时带尾注：4通道原始峰值 + L/R sum-squares + 帧数
```

## 七、k5 与 APEX6 Pro 的分野

| | k5 (APEX 4/5) | APEX 6 Pro |
|---|---|---|
| 握把 | ERM 电机 → 0x12 强度值 | 音圈 VCM → 0x57 PCM 波形流 |
| 触觉渲染 | 音频遥测包络 + 正弦载波（65/85/120/150Hz） | 原始 PCM 直推（94ms 使能延迟，gain 100-200%） |
| 扳机 | 0x51 结构化模式（本表） | 效果渲染成位置-阻力采样 |

## 八、给我们项目的启示

1. **按键位表死结的官方解**：读 XInput + EF 只补差 → ds_bridge_daemon 可直接采用
2. 触觉调色板可直接映射进它的翻译表（用户强度 0-200% 已内置）
3. 上游可提 PR 之处：k5 dongle 0x10 应答布局（[10]=校验和）——我们的 2 字节补丁可做成正式修复
4. 若要做"语义级手感增强"（如我们的调色板），挂点在 `translateAdaptiveTrigger` 一层

---
*源码快照：research/asb_src（git clone ReynArts/ApexSenseBridge @v1.0.1）。抓帧探针：probe_transport.py。*

