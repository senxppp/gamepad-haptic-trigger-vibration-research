"""
Flydigi APEX5 (八爪鱼5) 力反馈扳机驱动
======================================

通过实体手柄的厂商 HID 接口（usage page 0xFFA0）直接发送 32 字节命令帧，
驱动 L2/R2 力反馈扳机。协议逆向自 SpaceStationService.exe 的
SetForceTriggerCommandFactory（NewXInput 协议，cmdId 0x51），
与飞智空间站官方扳机管线同通道，两者可并存。

帧格式:
    byte[0]  HID 输出报文 ID = 0x03（0xFFA0 接口）
    byte[1]  0x5A  魔数
    byte[2]  0xA5  魔数
    byte[3]  0x51  力反馈扳机 cmdId（0x52 = 联动握把变体，本模块未用）
    byte[4]  0x0A  子命令
    byte[5]  0x01 生效 / 0x00 仅预览
    byte[6..] 效果参数: [side, mode, ...]，见下面六种模式
    byte[其余] 0x00 填充，总长 32 字节，即发即弃

效果模式（params = [side, mode, ...]）:
    mode 0 NORMAL    正常（复位）              [side, 0]
    mode 1 RACE      行程+阻力                 [side, 1, stroke, resistance, matchStroke]
    mode 2 SNIPER    狙击档位                  [side, 2, stroke, pressure, strength, frequency, matchStroke]
    mode 3 RECOIL    后座（单次重击）          [side, 3, stroke, recoilStroke, strength, 0, matchStroke]
    mode 4 LOCK      锁定（扳机变硬）          [side, 4, stroke, strength, matchStroke]
    mode 5 VIBRATION 扳机震动                  [side, 5, stroke, pressure, strength, frequency, matchStroke]

side: 1=左扳机(L2) 2=右扳机(R2) 3=双扳机
各强度/行程参数取值 1-255（0 会被官方代码强制抬到 1）。

★ 真机体感规律（2026-09-27 用户实测标定，写驱动时必须遵守）:
  1. VIBRATION 模式对 frequency 几乎不敏感（1/2/3/4 都有震感），
     但**必须与握把震动并发才可感知**——握把静止时扳机单独震动无感。
     中间层里发扳机震动前，先确保握把有同步驱动（哪怕低强度底震）。
  2. SNIPER 模式的 frequency 是"哒哒"节拍速度：低频=机枪式分顿，
     255≈连续震动（与 VIBRATION 无区别）。要机枪感用低频，要震感直接用 VIBRATION。
  3. RACE/LOCK/SNIPER 的阻力类效果不受上述限制，单独即可感知。

用法:
    from flydigi_trigger import FlydigiTrigger, BOTH
    trg = FlydigiTrigger()
    trg.open()
    trg.recoil(BOTH, stroke=255, recoil=120, strength=255)   # 后座
    trg.normal(BOTH)                                          # 复位
    trg.close()

命令行自测（六种效果轮流演示）:
    python flydigi_trigger.py demo
"""

import ctypes
import ctypes.wintypes as wt
import sys
import time

import hid  # hidapi，仅用于设备枚举

VID_FLYDIGI = 0x37D7
VENDOR_USAGE_PAGE = 0xFFA0

OUT_REPORT_ID = 0x03
FRAME_LEN = 32
CMD_FORCE_TRIGGER = 0x51
SUB_APPLY = 0x0A
FLAG_APPLY = 0x01

LEFT, RIGHT, BOTH = 1, 2, 3

MODE_NORMAL, MODE_RACE, MODE_SNIPER = 0, 1, 2
MODE_RECOIL, MODE_LOCK, MODE_VIBRATION = 3, 4, 5

# ---------- 感觉调色板（2026-09-27 真机标定，用户确认）----------
# 名称 → (模式, 参数)。参数可被 feel(name, **overrides) 覆盖。
# 阻力档位标定：150=过狠(弃) | 100=高速刹车/拉弓 | 60/30=日常油门刹车
# 机枪(Sniper)模式四参数 = 起始位置/压力/振动强度/频率；起始位置必须低（1~60），
# 255=行程末端，机构空转无感。VIBRATION 模式需握把同步震动才可感知。
PALETTE = {
    "机枪连发":   (MODE_SNIPER,  dict(start=1,  press=30,  viblevel=80,  freq=5)),
    "高射速机枪": (MODE_SNIPER,  dict(start=1,  press=30,  viblevel=80,  freq=15)),
    "持续嗡震":   (MODE_SNIPER,  dict(start=1,  press=30,  viblevel=120, freq=128)),
    "强刹车拉弓": (MODE_RACE,    dict(start=60, resistance=100)),
    "轻油门刹车": (MODE_RACE,    dict(start=60, resistance=60)),
    "微阻力":     (MODE_RACE,    dict(start=60, resistance=30)),
    "两段扳机":   (MODE_SNIPER,  dict(start=60, press=120, viblevel=0, freq=0)),
    "单发后座":   (MODE_RECOIL,  dict(start=1,  recoil_stroke=255, strength=255)),
    "扳机锁死":   (MODE_LOCK,    dict(start=40, strength=255)),
}


def find_vendor_path() -> str:
    """返回 APEX5 厂商接口（0xFFA0）的 HID 设备路径（自动适配所有飞智型号）。"""
    hits = []
    for d in hid.enumerate():
        if d["vendor_id"] == VID_FLYDIGI and d["usage_page"] == VENDOR_USAGE_PAGE:
            p = d["path"]
            hits.append((d["product_id"],
                         p.decode(errors="replace") if isinstance(p, bytes) else p))
    if not hits:
        raise RuntimeError(
            "未检测到飞智手柄的厂商接口（HID usage page 0xFFA0）。请检查手柄连接。")
    hits.sort(key=lambda t: t[0] != 0x2501)  # 八爪鱼5 优先
    return hits[0][1]


class FlydigiTrigger:
    """APEX5 力反馈扳机低层驱动。线程不安全；效果为持续型，需显式复位。"""

    def __init__(self):
        self._kernel32 = ctypes.WinDLL("kernel32")
        self._written = wt.DWORD(0)
        self._handle = None

    def open(self):
        path = find_vendor_path()
        h = self._kernel32.CreateFileA(path.encode(), 0xC0000000, 3, None, 3, 0, None)
        if h in (-1, 0xFFFFFFFFFFFFFFFF):
            raise OSError(f"打开 HID 设备失败: {ctypes.GetLastError()}")
        self._handle = h
        return self

    def close(self):
        if self._handle is not None:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        try:
            self.normal(BOTH)
        finally:
            self.close()

    # ---------- 底层 ----------

    def _send(self, params) -> bool:
        if self._handle is None:
            raise RuntimeError("设备未打开，先调用 open()")
        frame = bytearray(FRAME_LEN)
        frame[0] = OUT_REPORT_ID
        frame[1] = 0x5A
        frame[2] = 0xA5
        frame[3] = CMD_FORCE_TRIGGER
        frame[4] = SUB_APPLY
        frame[5] = FLAG_APPLY
        for i, b in enumerate(params):
            frame[6 + i] = max(0, min(255, int(b)))
        return bool(self._kernel32.WriteFile(self._handle, bytes(frame), FRAME_LEN,
                                             ctypes.byref(self._written), None))

    # ---------- 六种效果 ----------

    def normal(self, side=BOTH) -> bool:
        """复位为普通扳机。"""
        return self._send([side, MODE_NORMAL])

    def lock(self, side=BOTH, stroke=200, strength=200, match_stroke=True) -> bool:
        """锁定：扳机在 stroke 位置变硬。"""
        return self._send([side, MODE_LOCK, stroke, strength, 1 if match_stroke else 0])

    def race(self, side=BOTH, stroke=200, resistance=3, match_stroke=True) -> bool:
        """行进阻力：行程中段出现阻力。"""
        return self._send([side, MODE_RACE, stroke, max(1, resistance),
                           1 if match_stroke else 0])

    def sniper(self, side=BOTH, stroke=200, pressure=2, strength=200,
               frequency=20, match_stroke=True) -> bool:
        """狙击档位：分段阻力。"""
        return self._send([side, MODE_SNIPER, stroke, max(1, pressure),
                           max(1, strength), max(1, frequency),
                           1 if match_stroke else 0])

    def recoil(self, side=BOTH, stroke=255, recoil_stroke=120, strength=255,
               match_stroke=True) -> bool:
        """后座：开火瞬间的一次重击。射击游戏每发子弹调用一次。"""
        return self._send([side, MODE_RECOIL, stroke, recoil_stroke,
                           max(1, strength), 0, 1 if match_stroke else 0])

    def vibration(self, side=BOTH, stroke=255, pressure=3, strength=200,
                  frequency=20, match_stroke=True) -> bool:
        """扳机震动：持续嗡震。"""
        return self._send([side, MODE_VIBRATION, stroke, max(1, pressure),
                           max(1, strength), max(1, frequency),
                           1 if match_stroke else 0])

    # ---------- 感觉调色板 ----------

    def feel(self, name: str, side=BOTH, **overrides) -> bool:
        """按名字触发标定过的感觉；参数可覆盖。

        例: trg.feel("机枪连发")  trg.feel("强刹车拉弓", side=LEFT, resistance=150)
        可用名见 PALETTE。"""
        if self._handle is None:
            raise RuntimeError("设备未打开，先调用 open()")
        if name not in PALETTE:
            raise KeyError(f"未知感觉 '{name}'，可选：{list(PALETTE)}")
        mode, base = PALETTE[name]
        p = {**base, **overrides}
        if mode == MODE_SNIPER:
            return self._send([side, MODE_SNIPER, p["start"], max(1, p["press"]),
                               max(1, p["viblevel"]), max(1, p["freq"]),
                               1 if p.get("match", True) else 0])
        if mode == MODE_RACE:
            return self._send([side, MODE_RACE, p["start"], max(1, p["resistance"]),
                               1 if p.get("match", True) else 0])
        if mode == MODE_RECOIL:
            return self._send([side, MODE_RECOIL, p["start"], p["recoil_stroke"],
                               max(1, p["strength"]), 0,
                               1 if p.get("match", True) else 0])
        if mode == MODE_LOCK:
            return self._send([side, MODE_LOCK, p["start"], max(1, p["strength"]), 1])
        return self._send([side, MODE_NORMAL])


def _cli():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "demo"
    with FlydigiTrigger() as trg:
        if cmd == "demo":
            seq = [
                ("① Lock 锁定", lambda: trg.lock(BOTH, 200, 200)),
                ("② Vibration 震动", lambda: trg.vibration(BOTH, 255, 3, 200, 20)),
                ("③ Recoil 后座", lambda: trg.recoil(BOTH, 255, 120, 255)),
                ("④ Race 行程阻力", lambda: trg.race(BOTH, 200, 3)),
                ("⑤ Sniper 狙击档位", lambda: trg.sniper(BOTH, 200, 2, 200, 20)),
                ("⑥ Normal 复位", lambda: trg.normal(BOTH)),
            ]
            print("3 秒后开始，手指放 L2/R2", flush=True)
            time.sleep(3)
            for label, fn in seq:
                ok = fn()
                print(f"{time.strftime('%H:%M:%S')} {label} -> {ok}", flush=True)
                time.sleep(2.5)
        elif cmd == "off":
            print("复位:", trg.normal(BOTH))
        else:
            print(__doc__)
        print("完成")


if __name__ == "__main__":
    _cli()
