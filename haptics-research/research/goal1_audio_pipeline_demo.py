# -*- coding: utf-8 -*-
"""目标①管线演示：游戏触觉音频 → 虚拟DS音频端点 → 回环拦截 → 引擎 → k5 握把。

前置：viiper_host_keepalive.py 已在后台跑（虚拟 DS 存活）。
本脚本：
  A. 找到「DualSense Wireless Controller」渲染端点
  B. 往它播放 60Hz 低频测试音（模拟游戏的触觉音频流）
  C. 同时对该端点做 WASAPI Loopback 捕获 → RMS → k5 握把直发
"""
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\xpppj\.zcode\workspace\default\flydigi-music-haptic")
sys.path.insert(0, r"C:\Users\xpppj\.zcode\workspace\default\flydigi-haptic-middleware\vib_out")

import numpy as np
import pyaudiowpatch as pa
from flydigi_vib import FlydigiVibration

RATE = 48000
CH = 2
FRAME = 480  # 10ms


def make_burst_bass(t_now):
    """60Hz 底鼓脉冲（每 0.5 秒一记，指数衰减包络）。"""
    n = FRAME
    tt = (np.arange(n) + t_now) / RATE
    env = np.where((tt % 0.5) < 0.22, np.exp(-((tt % 0.5) % 0.22) / 0.06), 0.0)
    x = 0.9 * env * np.sin(2 * np.pi * 60 * tt)
    return (x * 0.6 * 32767).astype("<i2")


def main():
    p = pa.PyAudio()
    # 找虚拟 DS 的渲染端点
    ds_out = None
    try:
        for dev in p.get_loopback_device_info_generator():
            name = dev["name"]
            if "DualSense" in name:
                ds_out = dev
                break
    except Exception as e:
        print("枚举异常:", e)
    if ds_out is None:
        # 退化：按输出设备找
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info["maxOutputChannels"] > 0 and "DualSense" in info["name"]:
                ds_out = info
                break
    if ds_out is None:
        print("✗ 未找到 DualSense 渲染/回环端点（虚拟 DS 音频设备没起来？）")
        return 1
    print(f"✓ 目标端点: {ds_out['name']} (index {ds_out['index']})", flush=True)

    vib = FlydigiVibration()
    vib.open()
    print("✓ k5 握把通道已开", flush=True)

    t_now = 0
    t0 = time.perf_counter()
    print("开始 12 秒：60Hz 触觉音频 → 虚拟DS → 拦截 → k5 握把...", flush=True)
    try:
        # 渲染流（往虚拟 DS 播）
        out_stream = p.open(format=pa.paInt16, channels=CH, rate=RATE, output=True,
                            output_device_index=int(ds_out["index"]),
                            frames_per_buffer=FRAME)
        # 回环流（从虚拟 DS 拦截）
        lb_stream = p.open(format=pa.paInt16, channels=CH, rate=RATE,
                           input=True, input_device_index=int(ds_out["index"]),
                           frames_per_buffer=FRAME)
        while time.perf_counter() - t0 < 12.0:
            pcm = make_burst_bass(t_now)
            stereo = np.repeat(pcm[:, None], 2, axis=1).tobytes()
            out_stream.write(stereo)
            t_now += FRAME
            raw = lb_stream.read(FRAME, exception_on_overflow=False)
            arr = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(arr ** 2))) if arr.size else 0.0
            level = min(255, int(rms * 900))
            vib.set(level, level)
        out_stream.stop_stream(); out_stream.close()
        lb_stream.stop_stream(); lb_stream.close()
    finally:
        vib.stop(); vib.close(); p.terminate()
    print("演示结束，握把已归零。", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
