"""
Flydigi APEX5 (八爪鱼5) 私有协议震动输出驱动
============================================

通过实体手柄的厂商 HID 接口（usage page 0xFFA0）直接发送 32 字节命令帧驱动马达，
不依赖飞智空间站，DS 模式 / 普通模式下均可工作。

帧格式（逆向自 SpaceStationService.exe 的 Flydigi.ControllerSDK）:
    byte[0]  HID 输出报文 ID = 0x03（0xFFA0 接口描述符最后一个 ReportId 项）
    byte[1]  0x5A  魔数
    byte[2]  0xA5  魔数
    byte[3]  命令 ID（震动 = 0x12）
    byte[4]  0x06  子命令
    byte[5]  左握把马达 0-255
    byte[6]  右握把马达 0-255
    byte[7]  左扳机震动 0-255（IsSupportTriggerVibration 且 VibrationType ∈ {0,2} 时生效）
    byte[8]  右扳机震动 0-255
    byte[9..31] 0x00 填充

命令为即发即弃（fire-and-forget），控制器不回 ack。

用法:
    from flydigi_vib import FlydigiVibration
    vib = FlydigiVibration()
    vib.open()
    vib.set(left=255, right=255)      # 双握把全开
    vib.stop()
    vib.close()

命令行自测:
    python flydigi_vib.py test      # 三段脉冲：左 / 右 / 双
    python flydigi_vib.py sweep     # 双马达渐强 0->255
"""

import ctypes
import ctypes.wintypes as wt
import sys
import time

import hid  # hidapi，仅用于设备枚举

VID_FLYDIGI = 0x37D7
PID_APEX5 = 0x2501
VENDOR_USAGE_PAGE = 0xFFA0

OUT_REPORT_ID = 0x03
FRAME_LEN = 32
CMD_VIBRATION = 0x12


def find_vendor_path() -> str:
    """返回飞智手柄厂商接口（usage page 0xFFA0）的 HID 设备路径。

    自动扫描所有飞智设备（VID 0x37D7，不限型号）；有多个时优先
    八爪鱼5（PID 0x2501，协议已实测），其余型号按同族协议尝试。
    """
    hits = []
    for d in hid.enumerate():
        if d["vendor_id"] == VID_FLYDIGI and d["usage_page"] == VENDOR_USAGE_PAGE:
            path = d["path"]
            path = path.decode(errors="replace") if isinstance(path, bytes) else path
            hits.append((d["product_id"], path))
    if not hits:
        raise RuntimeError(
            "未检测到飞智手柄的厂商接口（HID usage page 0xFFA0）。请检查：\n"
            "  · 手柄已开机并与电脑连接（2.4G 接收器或 USB 线）\n"
            "  · 蓝牙直连方式可能不暴露该接口，请改用接收器/USB\n"
            "  · 设备管理器中能看到 Flydigi 相关 HID 设备"
        )
    hits.sort(key=lambda t: t[0] != PID_APEX5)  # 八爪鱼5 优先
    return hits[0][1]


class FlydigiVibration:
    """APEX5 震动马达低层驱动。线程不安全；持续震动需要周期性重发或按需 set(0)。"""

    def __init__(self):
        self._kernel32 = ctypes.WinDLL("kernel32")
        self._written = wt.DWORD(0)
        self._handle = None
        self._out_len = FRAME_LEN
        self._out_rid = OUT_REPORT_ID

    def open(self):
        k = self._kernel32
        path = find_vendor_path()
        h = k.CreateFileA(path.encode(), 0xC0000000, 3, None, 3, 0, None)
        if h in (-1, 0xFFFFFFFFFFFFFFFF):
            raise OSError(f"打开 HID 设备失败: {ctypes.GetLastError()} ({path[:60]}...)")
        self._handle = h
        self._probe_report_geometry(path)
        return self

    def _probe_report_geometry(self, path) -> None:
        """按连接的型号自适应报文几何（与飞智官方驱动同法）：

        输出报文长度取 HidP_GetCaps，报文 ID 取描述符最后一个 ReportId 项。
        八爪鱼5 上结果为 32 / 0x03；其他型号自动跟随其描述符。
        """
        try:
            hid_dll = ctypes.WinDLL("hid")
            pd = ctypes.c_void_p()
            if hid_dll.HidD_GetPreparsedData(self._handle, ctypes.byref(pd)):
                caps = (ctypes.c_ushort * 32)()
                if hid_dll.HidP_GetCaps(pd, caps) and caps[3] >= 9:
                    self._out_len = caps[3]
                hid_dll.HidD_FreePreparsedData(pd)
        except Exception:
            pass
        try:
            dev = hid.device()
            dev.open_path(path.encode() if isinstance(path, str) else path)
            desc = bytes(dev.get_report_descriptor())
            dev.close()
            rids = [desc[i + 1] for i, b in enumerate(desc)
                    if b == 0x85 and i + 1 < len(desc)]
            if rids:
                self._out_rid = rids[-1]
        except Exception:
            pass

    def close(self):
        if self._handle is not None:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        try:
            self.stop()
        finally:
            self.close()

    def set(self, left=0, right=0, trigger_left=0, trigger_right=0) -> bool:
        """设置四路马达强度（0-255）。0 即停止。"""
        if self._handle is None:
            raise RuntimeError("设备未打开，先调用 open()")
        frame = bytearray(self._out_len)
        frame[0] = self._out_rid
        frame[1] = 0x5A
        frame[2] = 0xA5
        frame[3] = CMD_VIBRATION
        frame[4] = 0x06
        frame[5] = max(0, min(255, int(left)))
        frame[6] = max(0, min(255, int(right)))
        frame[7] = max(0, min(255, int(trigger_left)))
        frame[8] = max(0, min(255, int(trigger_right)))
        ok = self._kernel32.WriteFile(self._handle, bytes(frame), self._out_len,
                                      ctypes.byref(self._written), None)
        return bool(ok)

    def stop(self) -> bool:
        return self.set(0, 0, 0, 0)

    def pulse(self, left=255, right=255, trigger_left=0, trigger_right=0, duration=0.5):
        """震动指定时长后归零（阻塞）。"""
        self.set(left, right, trigger_left, trigger_right)
        time.sleep(duration)
        self.stop()


def _cli():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"
    with FlydigiVibration() as vib:
        if cmd == "test":
            for label, kw in [("仅左握把", dict(left=255)),
                              ("仅右握把", dict(right=255)),
                              ("双握把", dict(left=255, right=255))]:
                print(f"{label} ...", flush=True)
                vib.pulse(duration=1.2, **kw)
                time.sleep(0.8)
        elif cmd == "sweep":
            for v in range(0, 256, 17):
                vib.set(v, v)
                time.sleep(0.12)
            vib.stop()
        elif cmd == "left":
            vib.pulse(left=int(sys.argv[2]) if len(sys.argv) > 2 else 255, duration=2)
        elif cmd == "right":
            vib.pulse(right=int(sys.argv[2]) if len(sys.argv) > 2 else 255, duration=2)
        else:
            print(__doc__)
        print("完成")


if __name__ == "__main__":
    _cli()
