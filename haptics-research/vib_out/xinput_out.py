"""
XInput 兼容输出层
=================

为不带飞智厂商接口的手柄（Xbox 等标准 XInput 手柄）提供震动输出，
走 Windows 自带的标准 XInput 震动 API（XInputSetState）。

与 HapticOutput 同接口（open / start / set_target / stop / stats / send_rate_hz），
由 pipeline 按 config.output.backend 二选一，其余代码互不感知。

马达语义对应（XInput 标准）：
  左握把（大节奏 / 低频） -> wLeftMotorSpeed  低频大马达
  右握把（细节 / 高频）   -> wRightMotorSpeed 高频小马达

强度换算：0-255 -> 0-65535（× 257）。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading
import time

from .haptic_out import OutputStats


class _XINPUT_VIBRATION(ctypes.Structure):
    _fields_ = [("wLeftMotorSpeed", wt.WORD),
                ("wRightMotorSpeed", wt.WORD)]


class _XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [("wButtons", wt.WORD),
                ("bLeftTrigger", ctypes.c_ubyte),
                ("bRightTrigger", ctypes.c_ubyte),
                ("sThumbLX", ctypes.c_short),
                ("sThumbLY", ctypes.c_short),
                ("sThumbRX", ctypes.c_short),
                ("sThumbRY", ctypes.c_short)]


class _XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", wt.DWORD),
                ("Gamepad", _XINPUT_GAMEPAD)]


def _load_xinput():
    """按优先级加载 XInput DLL（Win10/11 自带 xinput1_4）。"""
    for name in ("xinput1_4.dll", "xinput9_1_0.dll", "xinput1_3.dll"):
        try:
            dll = ctypes.WinDLL(name)
            dll.XInputGetState.restype = wt.DWORD
            dll.XInputGetState.argtypes = [wt.DWORD, ctypes.POINTER(_XINPUT_STATE)]
            dll.XInputSetState.restype = wt.DWORD
            dll.XInputSetState.argtypes = [wt.DWORD, ctypes.POINTER(_XINPUT_VIBRATION)]
            return dll
        except OSError:
            continue
    return None


class XInputOutput:
    """标准 XInput 手柄的震动输出层（接口与 HapticOutput 一致）。"""

    def __init__(self, send_rate_hz: float = 60.0, safety_max_drive: int = 240,
                 auto_stop_ms: float = 120.0, device_watchdog_s: float = 2.0,
                 **_ignored):
        self.send_rate_hz = max(10.0, send_rate_hz)
        self.safety_max = max(0, min(255, safety_max_drive))
        self.auto_stop_s = auto_stop_ms / 1000.0
        self.watchdog_s = device_watchdog_s
        self.stats = OutputStats()
        self._dll = _load_xinput()
        self._index = -1
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._target = (0, 0)
        self._target_ts = 0.0
        self._last_written = (-1, -1)
        self._last_watchdog = 0.0

    # ---------- 生命周期 ----------

    def open(self) -> "XInputOutput":
        self._find_device()
        self.stats.started_at = time.time()
        return self

    def _find_device(self) -> None:
        """在 0-3 号槽位里找第一个在线的 XInput 手柄。"""
        if self._dll is None:
            self.stats.connected = False
            return
        st = _XINPUT_STATE()
        for i in range(4):
            if self._dll.XInputGetState(i, ctypes.byref(st)) == 0:
                self._index = i
                self.stats.connected = True
                return
        self._index = -1
        self.stats.connected = False

    def start(self) -> "XInputOutput":
        if self._index < 0:
            self._find_device()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="xinput-out",
                                        daemon=True)
        self._thread.start()
        return self

    def stop(self, send_zero: bool = True) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.5)
            self._thread = None
        if send_zero:
            self._raw_write(0, 0)
        self.stats.connected = False

    def close(self) -> None:
        self.stop()

    def __enter__(self):
        return self.open().start()

    def __exit__(self, *exc):
        self.stop()

    # ---------- 目标投递 ----------

    def set_target(self, left: int, right: int) -> None:
        left = max(0, min(self.safety_max, int(left)))
        right = max(0, min(self.safety_max, int(right)))
        with self._lock:
            self._target = (left, right)
            self._target_ts = time.perf_counter()

    def stop_now(self) -> None:
        self.set_target(0, 0)

    # ---------- 写入线程 ----------

    def _loop(self) -> None:
        period = 1.0 / self.send_rate_hz
        next_t = time.perf_counter()
        while not self._stop.is_set():
            next_t += period
            with self._lock:
                left, right = self._target
                age = time.perf_counter() - self._target_ts
            if age > self.auto_stop_s:
                left = right = 0
            if (left, right) != self._last_written or left or right:
                self._raw_write(left, right)
            self._watchdog()
            sleep_for = next_t - time.perf_counter()
            if sleep_for > 0:
                time.sleep(sleep_for)
            else:
                next_t = time.perf_counter()

    def _raw_write(self, left: int, right: int) -> None:
        if self._dll is None or self._index < 0:
            self.stats.connected = False
            return
        vib = _XINPUT_VIBRATION(left * 257, right * 257)
        if self._dll.XInputSetState(self._index, ctypes.byref(vib)) == 0:
            self._last_written = (left, right)
            self.stats.last_left, self.stats.last_right = left, right
            self.stats.note_send()
            self.stats.connected = True
        else:
            self.stats.write_failures += 1
            self.stats.connected = False
            self._index = -1

    def _watchdog(self) -> None:
        """手柄拔出后周期性重扫（与 HapticOutput 同语义）。"""
        now = time.perf_counter()
        if now - self._last_watchdog < self.watchdog_s:
            return
        self._last_watchdog = now
        if self._index < 0:
            self._find_device()
            if self._index >= 0:
                self.stats.reconnects += 1
                self._last_written = (-1, -1)
