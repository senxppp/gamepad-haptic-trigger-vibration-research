"""
PWM 细腻模式调制器
==================

转子马达（ERM）转速无法电子调节，但可以用占空比斩波"骗"出中间强度：
高于写入频率一半的开关切换会被转子惯性平均掉。

两档语义（对每个通道独立）：
  目标 > floor：在 target 和 floor 之间斩波 —— 平均强度 ≈ duty×target+(1-duty)×floor，
                强震动变得"细"、可控；
  0 < 目标 ≤ floor：在 floor 和 0 之间打脉冲 —— 低于启动门限的弱目标"活过来"，
                变成可感知的弱震颤（否则会被门限直接掐死）；
  目标 = 0：静默。

参数 v1（固定值，GUI 只给开关）：
  hz=25    斩波频率。游戏版写入 60Hz、音乐版 100Hz，25Hz 保证每周期 ≥2 次写入；
  duty=0.55 占空比；
  floor=30 保活底值（实测启动门限 ≤15/255，30 留一倍余量）。
"""

from __future__ import annotations

import time

PWM_HZ = 25.0
PWM_DUTY = 0.55
PWM_FLOOR = 30


class PwmModulator:
    """按时间相位做占空比斩波；目标为零时直通并复位相位。"""

    def __init__(self, enabled: bool = False, hz: float = PWM_HZ,
                 duty: float = PWM_DUTY, floor: int = PWM_FLOOR):
        self.enabled = enabled
        self.hz = max(1.0, hz)
        self.duty = min(0.95, max(0.05, duty))
        self.floor = max(0, min(255, floor))
        self._phase = 0.0
        self._last_t: float | None = None

    def apply(self, left: int, right: int) -> tuple[int, int]:
        if not self.enabled or (left <= 0 and right <= 0):
            self._last_t = None
            return left, right
        now = time.perf_counter()
        if self._last_t is None:
            self._last_t = now
        self._phase += (now - self._last_t) * self.hz
        self._last_t = now
        on = (self._phase % 1.0) < self.duty

        def ch(v: int) -> int:
            if v > self.floor:
                return v if on else self.floor
            if v > 0:
                return self.floor if on else 0
            return 0

        return ch(left), ch(right)
