# 研究结论全集（FINDINGS）

> 全部结论真机实测。机器：Windows 11 26200 x64，飞智八爪鱼5（VID_37D7 PID_2501），
> 飞智空间站 4.2.2.3（D:\Flydigi Space Station\）。

---

## 1. 握把震动私有协议（已破解）

- 通道：实体手柄厂商 HID 集合 **VID_37D7 / usage_page 0xFFA0（MI_02 Col01）**，
  输出报文 32 字节、报文 ID 0x03。
- 帧格式：`[0]=0x03 [1]=0x5A [2]=0xA5 [3]=cmdId [4..]=参数`
- 震动：cmdId=0x12，[4]=0x06，[5]=左握把 [6]=右握把（0-255），即发即弃无 ack。
- 与空间站并存无冲突（同接口，服务心跳为周期突发）。
- 已知 cmdId：0x01 心跳 0x02 昵称 0x03 硬件状态 0x04 UID 0x10 原始数据
  0x12 震动 0xA3 映射读。

## 2. 力反馈扳机协议（已破解 + 标定）

- 帧：`[0]=0x03 [1]=5A [2]=A5 [3]=cmdId [4]=0x0A [5]=01生效 [6..]=参数`，
  参数首两字节 `[side, mode]`（side 1左/2右/3双）。
- cmdId 0x51（普通）/ 0x52（联动握把变体，[4]=0x0B，服务端 bindType=2）。

| mode | 效果 | 参数 |
|---|---|---|
| 0 | 复位 | — |
| 1 RACE | 行程阻力 | Start, Resistance, Match |
| 2 SNIPER | 段落+振动 | Start, PressLevel, VibrationLevel, VibrationFrequency, Match |
| 3 RECOIL | 后座 | Start, RecoilStroke, Strength, 0, Match |
| 4 LOCK | 锁定 | Start, Strength, Match |
| 5 VIBRATION | 扳机震动 | Stroke, Pressure, Strength, Frequency, Match |

- **UI 模式名交叉**：空间站 UI"机枪"=SNIPER(2)、UI"狙击"=RECOIL(3)。

### 真机标定（用户体感，硬规则）

1. **Start（起始位置）必须低（1~60）**：效果是位置型的——Start=255 机构在行程
   末端空转，只响不震（踩坑半天的根源）。
2. VIBRATION 模式对频率不敏感（1/2/3/4 都有感），但**必须握把同步震动才可感知**。
3. SNIPER 的 frequency = 哒哒节拍速度：低频=机枪分顿，255≈连续震动。
4. RACE/LOCK 阻力类单独即可感知。

### 感觉调色板（已封装 flydigi_trigger.py 的 PALETTE/feel()）

| 名称 | 配方 |
|---|---|
| 机枪连发 | SNIPER Start=1 Press=30 Vib=80 Freq=5 |
| 高射速机枪 | 同上 Freq=15 |
| 持续嗡震 | SNIPER Start=1 Press=30 Vib=120 Freq=128 |
| 强刹车拉弓 | RACE Start=60 Resistance=100 |
| 轻油门刹车 | RACE Start=60 Resistance=60 |
| 微阻力 | RACE Start=60 Resistance=30（150 过狠已弃）|
| 两段扳机 | SNIPER Start=60 Press=120 Vib=0 Freq=0 |
| 单发后座 | RECOIL Start=1 Recoil=255 Strength=255 |
| 扳机锁死 | LOCK Start=40 Strength=255 |

- 用户调好的参数保存在 `Configs/Controller/k5/{cache,onboard}/<uid>.dat`
  （Protobuf，schema 在 SharedResources.Data.Protobuf：Sniper 字段 1=Start
  2=PressLevel 3=VibrationLevel 4=VibrationFrequency 5=MatchStart）——可读取用户偏好。
- ⚠ 直发帧与空间站 UI 写同一状态存储，后写者生效，勿同时调。

## 3. 空间站 DS 模式架构

- 进程模拟（重命名任意 exe 为游戏进程名）触发 `OnGameModStart` → 手柄重枚举进 DS 模式：
  物理 XInput 消失，出现虚拟 DualSense VID_054C PID_0CE6。
- 虚拟驱动 `hidvirtualdriver.sys` = 魔改 ViGEmBus（GeniTech fork）。
- 虚拟 DS 描述符：DS4 风格混合体，输出**只收 0x02（47B 厂商数据）**，0x31 拒收（err 87）。
- 已知坑：游戏进程异常退出时 `OnGameModClose` 不触发 → DS 模式卡死 →
  重启 "Flydigi Space Station Service"（需管理员）解除。

## 4. 万维自适应扳机（视觉触发）→ 85 直通

- 万维（Gaming Adaptive Trigger.exe，C# WinForms + OpenCvSharp）视觉识别 →
  **UDP 127.0.0.1:7878 JSON** → 后端（DS 走 Control 里的 JoyShockMapper；
  八爪鱼3/4 走旧版 FlydigiPcSpace）。
- 包格式：`{"instructions":[{"type":1,"parameters":[0,side,19,"mode","p1","p2","p3","p4"]},...]}`
  parameters 必须是真 JSON 数组（字符串包裹会解析失败）。
  mode 0常规 1阻力(p1起始,p2力度) 2振动(p1起始,p2力度,p3频率) 3段落(p1起始,p2行程,p3阻力)。
- **现役空间站 4.2.2.3 的 AdapterTriggerService 就监听 7878**（官方 Mod 通道），
  实测把万维指令直接翻译成 k5 ForceTrigger 帧服务日志实锤。
- → **万维里选八爪鱼3/4，85 原生可用**（虽然 UI 没列 85）。
- `wanwei_k5_bridge.py` = 无空间站机器的备胎桥（绑 7878 直发 k5）。

## 5. APEXtoDS（八爪鱼6 脱离空间站的 DS 模拟）

- 架构：usbip-win2 0.9.8（虚拟 USB 主机，服务 usbip2_ude/usbip2_filter）+
  **libVIIPER.dll（开源 Go 库 github.com/Alia5/VIIPER 的私有 ASB 扩展构建）** +
  HidHide（藏物理手柄）+ C++ 翻译层（apex6_gui，内置 audio_haptics::MonitorPlayback）。
- libVIIPER 导出 C API：CreateUSBBus/CreateDualSenseDevice(Edge)/
  SetDualSenseOutputCallback/SetDualSenseASBRawOutputCallback（音频触觉原始流）/
  SetDualSenseDeviceState。Go 符号：dualsense.ASBOutputState/AudioHapticsState/
  FeedbackFrame/dsedgehandler；asb_extensions.go/asb_descriptor.go（私有）。
- 只支持 APEX6（PID 0x2502）；85 需加 HID 通道（可向作者提需求）。
- 已知坑：异常退出残留 HidHide 隐藏规则 → 官方软件看不到手柄
  （86p触觉反馈bug救星.zip = 清 HidHide 配置）。
- 86p 能用 DS5 触觉软件的原理：虚拟 DS 带真实音频端点，触觉即音频。

## 6. 虚拟 DualSense 宿主（本项目复刻 APEXtoDS 骨架）

- usbip-win2 静默安装无需重启；libVIIPER.dll 可从 Python ctypes 直接宿主：
  `NewUSBServer(cfg{addr="0.0.0.0:3241",30000,5000,1}) → CreateUSBBus →
   CreateDualSenseDevice(autoAttachLocalhost=True)` → 虚拟 DS5 稳定枚举
  （HID 手柄 + **MEDIA 音频设备 4ch/48kHz 扬声器 + 2ch 麦克风**）。
- 输入喂入：k5 XInputGetState → SetDualSenseDeviceState（6385/6385 帧）。
- ⚠ 虚拟声卡就绪需 ~10 秒，过早开流报 -9999（竞态）。
- ⚠ 虚拟 DS 的 HID 输出只收 0x02：payload[2]=rumbleSmall payload[3]=rumbleLarge
  （活体探针破解）；payload[0]/[1]=控制字节（0xFF 整包丢弃）；LED/更深字段被门控。
- 音频触觉管线（全链路验证）：触觉音频 → 虚拟 DS 扬声器 → WASAPI Loopback →
  RMS/瞬态分析 → k5 握把 + 扳机感觉（1157 帧 0 丢帧；goal1/goal2 演示脚本）。

## 7. 发布工程经验

- GitHub 无 git CLI 时：REST API + device flow（client_id 178c6fc778ccc68e1d6a，
  scope=repo）；curl 上传附件必须 `--data-binary @"文件"`（漏 @ 会把路径字符串当
  文件体，HTTP 201 但内容 85B）；上传后必须回读 name+size。
- Release 附件名必须纯 ASCII。
- .NET 单文件反编译：`ilspycmd --bundle-entry <程序集> <exe>`。
- 音乐版 `Engine(**params)` 整字典传参——新增配置键必须加入
  `_engine_params()` 排除表，否则启动崩溃（踩过）。
- PyInstaller：动态 import 模块必须 hiddenimports 显式声明 + pathex。
- 控制台 GBK：`sys.stdout.reconfigure(encoding="utf-8", errors="replace")` +
  避免打印 ✓ 等字符（或包安全打印）。

## 8. 未解/待续

- 虚拟 DS 0x02 载荷的 LED/触发器分节格式（活体探针框架就绪：probe_0x02.py）。
- DS 原生 0x31 输出进虚拟 DS：需扩展 VIIPER 描述符+解析器（Go，~1天），
  或向 Alia5 提 issue（其私有 ASB 分支可能已含）。
- 音频触觉流的 Haptify 式精确解码（当前 RMS 近似对转子够用）。
- k5 高频写入稳定性长测；蓝牙 vs USB 差异。


---

# 2026-10-10~11 追加：C 线（APEXtoDS 强改八爪鱼5）+ 原始输入流

> EF 帧布局细节见 APEX6-EF帧布局逆向-进行中.md（docs/）

## 9. APEXtoDS 强改八爪鱼5（基于他人成果，细节不公开）

APEXtoDS 0.5.1.1（八爪鱼6 专用 DS→扳机翻译工具，作者另案发布）经补丁改造可驱动八爪鱼5。
本项目在其基础上规划了输入翻译层（k5 原始流按键位 → APEX6 位布局）。
尊重原作者成果，改造细节不在此公开；本仓库只含自研的工具与协议研究。

## 10. 原始输入流使能 + EF 帧结构（重要）

**使能命令**（cmdId 0x11）：`[03][5A A5][11][07][ctrl][raw][kbd][mouse][3p][crc]`
- 开关：1=开 0=关 255=不变；crc = sum(buf[3..3+7]) & 0xFF
- **键盘/鼠标必须 = 0**（开 1 会把手柄切进键鼠模式，踩坑两次）
- 全开 148Hz EF motion 流；服务停止后自建宿主也可使能。

**EF motion 帧**（32B）：`04 5A A5 EF [4..31]`
- [4] = 子类型字段（不同子类型布局不同——分析时必须按子类型分组！）
- 输入状态子类型：按键区 + 陀螺仪/加速度（六对 16 位 BE @ [19..30]）
- 按键位表（标准配置 kbd=0/mouse=0 下标定）：
  A=字节12.bit4、B=字节12.bit5、L3=字节13.bit6（时间顺序裁决确认）；
  X/Y/LB/RB/BACK/十字/LT/RT 待标准配置下重测（首轮标定在旧配置下，位表作废）。
- 异步 OVERLAPPED ReadFile 才能收到流（GetInputReport 只是静态快照）；
  虚拟声卡就绪需 ~10s；WriteFile err=997 是异步正常成功。

## 11. 陀螺仪→鼠标模式之谜

- 使能命令键盘/鼠标开关全开 → 手柄切键鼠模式 + 陀螺仪驱动鼠标（空间站服务层功能）。
- 修正：控制器=1 原始=1 键盘=0 鼠标=0；彻底复位需拔插手柄。
- 残留进程坑：TaskStop 后 python 子进程可能存活且卡死在内核 HID 读取
  （taskkill /F 报"操作不被支持"）→ 拔插手柄解套。
- 多实例坑：同时跑两个守护进程 = 两个虚拟 DS + 两套喂入打架（"映射神奇"事故）。
  单实例纪律：启动前 tasklist 查 python。
