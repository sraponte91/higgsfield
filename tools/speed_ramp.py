"""Speed-ramp a clip: smooth speed curve, shutter-style blur in fast sections, interpolated slow motion.

1. ffmpeg motion-interpolates the source to a high frame rate (default 120 fps).
2. A speed curve (source time -> speed, smoothly eased between keyframes) maps every output
   frame to a span of source time.
3. Each output frame averages the interpolated frames inside its span, so fast sections get
   real motion blur and slow sections stay sharp.

Usage:
  python tools/speed_ramp.py in.mp4 out.mp4 --ffmpeg /path/to/ffmpeg \
      --keys "0:1,0.5:1,0.8:2.6,2.7:2.6,3.1:0.35,3.5:0.35,4.04:1" --fps 60
Keys are "source_seconds:speed" pairs; speed 2 = twice as fast, 0.5 = half speed.
Needs numpy and Pillow.
"""
import argparse
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


def smoothstep(u: float) -> float:
    return u * u * (3 - 2 * u)


def speed_at(t: float, keys: list[tuple[float, float]]) -> float:
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, s0), (t1, s1) in zip(keys, keys[1:]):
        if t <= t1:
            return s0 + (s1 - s0) * smoothstep((t - t0) / (t1 - t0))
    return keys[-1][1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('out')
    ap.add_argument('--ffmpeg', default='ffmpeg')
    ap.add_argument('--keys', required=True)
    ap.add_argument('--fps', type=int, default=60, help='output frame rate')
    ap.add_argument('--interp-fps', type=int, default=120, help='intermediate interpolated frame rate')
    ap.add_argument('--crf', type=int, default=14)
    a = ap.parse_args()

    keys = sorted((float(k), float(v)) for k, v in (p.split(':') for p in a.keys.split(',')))
    work = Path(tempfile.mkdtemp(prefix='ramp_'))
    try:
        # 1. Motion-interpolate to a high frame rate and dump frames.
        subprocess.run([a.ffmpeg, '-v', 'error', '-y', '-i', a.src,
                        '-vf', f"minterpolate=fps={a.interp_fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,format=rgb24",
                        str(work / 'f%05d.png')], check=True)
        frames = sorted(work.glob('f*.png'))
        n = len(frames)
        src_dur = n / a.interp_fps

        # 2. Integrate the speed curve: output time advances by dt_src / speed.
        step = 1 / (a.interp_fps * 8)
        out_time, src_time, table = 0.0, 0.0, [(0.0, 0.0)]
        while src_time < src_dur:
            out_time += step / speed_at(src_time + step / 2, keys)
            src_time += step
            table.append((out_time, src_time))
        total_out = table[-1][0]
        outs = np.array([o for o, _ in table])
        srcs = np.array([s for _, s in table])

        def src_for(t_out: float) -> float:
            return float(np.interp(t_out, outs, srcs))

        # 3. Build each output frame by averaging the source frames inside its time span.
        cache: dict[int, np.ndarray] = {}

        def frame(i: int) -> np.ndarray:
            i = min(max(i, 0), n - 1)
            if i not in cache:
                if len(cache) > 64:
                    cache.pop(next(iter(cache)))
                cache[i] = np.asarray(Image.open(frames[i]), dtype=np.float32)
            return cache[i]

        out_dir = work / 'out'
        out_dir.mkdir()
        n_out = math.floor(total_out * a.fps)
        for k in range(n_out):
            s0, s1 = src_for(k / a.fps), src_for((k + 1) / a.fps)
            i0, i1 = int(s0 * a.interp_fps), max(int(s0 * a.interp_fps) + 1, int(math.ceil(s1 * a.interp_fps)))
            acc = sum(frame(i) for i in range(i0, i1)) / (i1 - i0)
            Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8)).save(out_dir / f'o{k:05d}.png')

        subprocess.run([a.ffmpeg, '-v', 'error', '-y', '-framerate', str(a.fps), '-i', str(out_dir / 'o%05d.png'),
                        '-c:v', 'libx264', '-crf', str(a.crf), '-preset', 'slow', '-pix_fmt', 'yuv420p',
                        '-movflags', '+faststart', a.out], check=True)
        print(f'{n} interpolated source frames ({src_dur:.2f}s) -> {n_out} output frames ({n_out / a.fps:.2f}s at {a.fps} fps)')
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
