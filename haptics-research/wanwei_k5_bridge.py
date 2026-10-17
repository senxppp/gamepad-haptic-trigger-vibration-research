"""
万维自适应扳机 → 飞智八爪鱼5 桥接器
====================================

万维自适应扳机（视觉识别）对八爪鱼3/4 的扳机指令走
UDP 127.0.0.1:7878 的 JSON 包（本机回环），由旧版 FlydigiPcSpace
接收翻译。但旧版不认识八爪鱼5 —— 本桥接器**顶替它**监听 7878，
把指令实时翻译成八爪鱼5 的力反馈扳机帧（NewXInput 协议 cmdId 0x51）。

万维侧协议（逆向自 Gaming Adaptive Trigger.exe + FlydigiPcSpace.exe）:
    {"instructions":[
        {"type":1, "parameters":[0, side, 19, mode, p1, p2, p3, p4]},
        {"type":0, "parameters":null}, ...]}
    side: 1=左扳机 2=右扳机
    mode: 0=常规 1=阻力 2=振动 3=段落
    阻力:   p1=阻尼起始位置  p2=阻尼力度
    振动:   p1=起始位置      p2=振动力度  p3=振动频率
    段落:   p1=起始位置      p2=持续行程  p3=阻力
    （parameters 可能是内嵌 JSON 字符串或数组，两种都兼容）

用法:
    1. 关闭旧版 FlydigiPcSpace（它会抢占 7878 端口）
    2. python wanwei_k5_bridge.py
    3. 万维自适应扳机里把手柄选成「飞智八爪鱼3」或「八爪鱼4」
       （桥接器按八爪鱼5 的协议翻译，选哪个都能用）
    4. 正常使用万维的视觉识别功能即可
"""

import json
import socket
import sys
import threading

import ctypes
import ctypes.wintypes as wt

import hid  # hidapi 枚举用

UDP_PORT = 7878
VID_FLYDIGI = 0x37D7
VENDOR_USAGE_PAGE = 0xFFA0
OUT_REPORT_ID = 0x03
FRAME_LEN = 32
CMD_FORCE_TRIGGER = 0x51
SUB_APPLY = 0x0A

LEFT, RIGHT = 1, 2

# 万维模式 → (k5模式, 参数取法)
#   k5 参数表: RACE=[stroke, resistance, match]
#              VIBRATION=[stroke, pressure, strength, frequency, match]
#              SNIPER=[stroke, pressure, strength, frequency, match]
def clamp(v, lo=0, hi=255):
    return max(lo, min(hi, int(v)))


def translate(side: int, mode: int, p) -> list:
    """万维 [mode, p1..p4] → k5 参数列表（[side, k5mode, ...]）。"""
    if mode == 0:
        return [side, 0]
    if mode == 1:   # 阻力: p1=起始位置→stroke, p2=力度→resistance
        return [side, 1, clamp(p[0] or 200), clamp(p[1] or 3), 1]
    if mode == 2:   # 振动: p1=起始→stroke, p2=力度→strength, p3=频率→frequency
        return [side, 5, clamp(p[0] or 255), 2, clamp(p[1] or 200),
                clamp(p[2] or 20), 1]
    if mode == 3:   # 段落: p1=起始→stroke, p2=行程, p3=阻力→pressure
        return [side, 2, clamp(p[0] or 200), clamp(p[2] or 2),
                clamp(p[1] or 200), 10, 1]
    return [side, 0]


class K5TriggerSender:
    """0xFFA0 接口的力反馈扳机帧直发（同 flydigi_trigger.py）。"""

    def __init__(self):
        self._kernel32 = ctypes.WinDLL("kernel32")
        self._written = wt.DWORD(0)
        self._handle = None
        self._last = {}

    def open(self):
        hits = []
        for d in hid.enumerate():
            if d["vendor_id"] == VID_FLYDIGI and d["usage_page"] == VENDOR_USAGE_PAGE:
                p = d["path"]
                hits.append((d["product_id"],
                             p.decode(errors="replace") if isinstance(p, bytes) else p))
        if not hits:
            raise RuntimeError("未找到飞智手柄厂商接口（0xFFA0）")
        hits.sort(key=lambda t: t[0] != 0x2501)
        h = self._kernel32.CreateFileA(hits[0][1].encode(), 0xC0000000, 3,
                                       None, 3, 0, None)
        if h in (-1, 0xFFFFFFFFFFFFFFFF):
            raise OSError(f"打开 HID 失败: {ctypes.GetLastError()}")
        self._handle = h

    def send(self, params) -> bool:
        if self._handle is None:
            return False
        frame = bytearray(FRAME_LEN)
        frame[0] = OUT_REPORT_ID
        frame[1] = 0x5A
        frame[2] = 0xA5
        frame[3] = CMD_FORCE_TRIGGER
        frame[4] = SUB_APPLY
        frame[5] = 0x01
        for i, b in enumerate(params):
            frame[6 + i] = clamp(b)
        return bool(self._kernel32.WriteFile(self._handle, bytes(frame), FRAME_LEN,
                                             ctypes.byref(self._written), None))

    def close(self):
        if self._handle is not None:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


def handle_packet(data: bytes, sender: K5TriggerSender, log) -> None:
    try:
        packet = json.loads(data.decode("utf-8", errors="replace"))
    except Exception as e:
        log(f"✗ 非 JSON 包（{len(data)}B）: {e}")
        return
    for ins in packet.get("instructions") or []:
        try:
            if ins.get("type") != 1:
                continue
            p = ins.get("parameters")
            if isinstance(p, str):
                p = json.loads(p)
            if not p or len(p) < 8:
                continue
            side, cmd, mode = int(p[1]), int(p[2]), int(p[3])
            if cmd != 19 or side not in (LEFT, RIGHT):
                continue
            k5 = translate(side, mode, p[4:8])
            key = f"L{side}" if side == LEFT else f"R{side}"
            if sender._last.get(key) == k5:
                continue          # 与上次相同，跳过（同官方去重逻辑）
            sender._last[key] = k5
            ok = sender.send(k5)
            log(f"{'左' if side == LEFT else '右'}扳机 万维mode{mode} → k5{k5} {'✓' if ok else '✗'}")
        except Exception as e:
            log(f"✗ 指令处理异常: {e}")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else UDP_PORT
    sender = K5TriggerSender()
    sender.open()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError as e:
        print(f"✗ {port} 端口被占用（旧版 FlydigiPcSpace 在跑？请先关掉它）: {e}")
        return 1

    print(f"✓ 万维→八爪鱼5 桥接器已启动，监听 UDP 127.0.0.1:{port}")
    print("  在万维自适应扳机中把手柄选为「飞智八爪鱼3/4」即可。Ctrl+C 退出。")
    stop = threading.Event()

    def idle_reset():
        # 长时间无指令时不动手柄（效果是持续型，交给万维管理）
        while not stop.is_set():
            time.sleep(1)

    import time
    threading.Thread(target=idle_reset, daemon=True).start()
    try:
        while True:
            data, addr = sock.recvfrom(4096)
            handle_packet(data, sender, lambda m: print(m, flush=True))
    except KeyboardInterrupt:
        print("\n退出。")
    finally:
        stop.set()
        sock.close()
        sender.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
