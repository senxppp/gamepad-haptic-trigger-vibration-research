# -*- coding: utf-8 -*-
"""目标②管线演示：游戏原声 → 虚拟DS拦截 → 音频事件合成 → k5 力反馈扳机。

前置：viiper_host_keepalive.py 后台运行（虚拟 DS 存活）。
音频设计（模拟 FPS 场景）：
  · 枪声（白噪声瞬态爆发）→ R2 RECOIL 后座（每发一记）
  · 持续低频（引擎/爆炸尾音）→ 握把震动 + R2 扳机 VIBRATION
分析：能量通量瞬态检测（帧 RMS 对滑动基线的跳变）+ 不应期。
"""
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\xpppj\.zcode\workspace\default\flydigi-music-haptic")
sys.path.insert(0, r"C:\Users\xpppj\.zcode\workspace\default\flydigi-haptic-middleware\vib_out")

import numpy as np
import pyaudiowpatch as pa
from flydigi_vib import FlydigiVibration
from flydigi_trigger import FlydigiTrigger, RIGHT, LEFT, BOTH

RATE, CH, FRAME = 48000, 4, 480
rng = np.random.default_rng(7)


def make_scene_frame(t_now):
    """模拟 FPS 原声：随机枪声（噪声瞬态）+ 周期性低频引擎声。"""
    tt = (np.arange(FRAME) + t_now) / RATE
    x = np.zeros(FRAME)
    # 引擎：持续 55Hz 低频（弱）
    x += 0.25 * np.sin(2 * np.pi * 55 * tt)
    # 枪声：由主循环按事件注入
    return x


def make_gunshot(n=FRAME):
    """白噪声瞬态 + 低频砰，指数衰减。"""
    tt = np.arange(n) / RATE
    noise = rng.standard_normal(n) * np.exp(-tt / 0.012)
    boom = 0.8 * np.sin(2 * np.pi * 70 * tt) * np.exp(-tt / 0.03)
    return (noise * 0.5 + boom) * 0.85


def main():
    p = pa.PyAudio()
    vib = FlydigiVibration()
    vib.open()
    trg = FlydigiTrigger()
    trg.open()

    out_stream = p.open(format=pa.paInt16, channels=CH, rate=RATE, output=True,
                        output_device_index=13, frames_per_buffer=FRAME)
    lb_stream = p.open(format=pa.paInt16, channels=CH, rate=RATE, input=True,
                       input_device_index=17, frames_per_buffer=FRAME)

    baseline = 0.0005     # 滑动能量基线
    last_shot = -1.0      # 上次扳机后座时刻（不应期）
    t_now = 0
    shots = 0
    t0 = time.perf_counter()
    scene_t = 0.0
    print("✓ 15 秒：模拟FPS原声（随机枪声+引擎）→ 拦截 → R2后座/握把", flush=True)
    try:
        next_shot_at = 0.4
        while time.perf_counter() - t0 < 15.0:
            x = make_scene_frame(t_now)
            # 场景事件：到点注入枪声（进入渲染流）
            wall = time.perf_counter() - t0
            if wall >= next_shot_at:
                gs = make_gunshot()
                x = x + gs[:FRAME] if gs.size >= FRAME else x + gs
                next_shot_at = wall + rng.uniform(0.35, 1.1)
            x = np.clip(x, -1, 1)
            pcm = (x * 0.5 * 32767).astype("<i2")
            out_stream.write(np.repeat(pcm[:, None], CH, axis=1).tobytes())
            t_now += FRAME

            # 拦截 + 分析
            raw = lb_stream.read(FRAME, exception_on_overflow=False)
            arr = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(arr ** 2))) if arr.size else 0.0
            wall = time.perf_counter() - t0

            # 1) 瞬态检测 → R2 后座
            ratio = rms / max(baseline, 1e-5)
            if rms > 0.004 and ratio > 2.2 and wall - last_shot > 0.12:
                trg.recoil(RIGHT, stroke=255, recoil_stroke=140, strength=255)
                last_shot = wall
                shots += 1
                print(f"  🔫 {wall:5.2f}s 枪声瞬态 (rms={rms:.4f} ×{ratio:.1f}) → R2后座", flush=True)
            # 2) 持续能量 → 握把（含底噪让扳机震动可感知）+ 扳机震动
            level = min(255, int(rms * 1500))
            vib.set(level, max(30, level))
            if level > 60:
                trg.vibration(BOTH, stroke=255, pressure=2, strength=min(200, level), frequency=8)
            baseline = 0.9 * baseline + 0.1 * rms
    finally:
        vib.stop(); vib.close()
        trg.normal(BOTH); trg.close()
        out_stream.stop_stream(); out_stream.close()
        lb_stream.stop_stream(); lb_stream.close()
        p.terminate()
    print(f"✓ 完成。共合成 {shots} 次R2后座。", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
