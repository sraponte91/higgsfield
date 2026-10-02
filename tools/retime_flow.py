"""Smooth frame-rate conversion with optical flow (e.g. a 24 fps render to 29.97 fps for a 30 fps timeline).

Output frames that land on a source frame (within 5% of a frame) copy it untouched; the rest are built from
the two neighbouring source frames with dense optical flow (OpenCV DIS) in both directions, blended with
forward/backward consistency weights so occluded pixels come from the side that sees them. Flow is computed
at 1080 wide and applied at full resolution. Never interpolates across a cut.

With DEDUPE=1, frames that repeat the previous one (footage that only updates every other frame) are dropped
and the remaining real frames are spaced evenly through each shot before resampling, so the motion becomes
continuous instead of move-freeze-move.

Usage: python tools/retime_flow.py <frames_dir> <src_fps> <out_dir> <out_fps> <duration_s> [cut_frame ...]
Frames are f001.png ... (8- or 16-bit). cut_frame = 1-based index of the first frame of a new shot.
"""
import os
import sys
from pathlib import Path

import cv2
import numpy as np

SRC, SRC_FPS, OUT, OUT_FPS, DUR = Path(sys.argv[1]), float(sys.argv[2]), Path(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
CUTS = sorted(int(c) for c in sys.argv[6:])
OUT.mkdir(parents=True, exist_ok=True)
files = sorted(SRC.glob('f*.png'))
cache = {}


def load(i):                                   # 0-based
    if i not in cache:
        if len(cache) > 6:
            cache.pop(next(iter(cache)))
        a = cv2.imread(str(files[i]), cv2.IMREAD_UNCHANGED)
        cache[i] = a.astype(np.float32) / (65535.0 if a.dtype == np.uint16 else 255.0)
    return cache[i]


dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)


def small_gray(a):
    h, w = a.shape[:2]
    s = cv2.resize(a, (1080, round(h * 1080 / w)), interpolation=cv2.INTER_AREA)
    return (cv2.cvtColor(s, cv2.COLOR_BGR2GRAY) * 255).astype(np.uint8)


def remap(img, flow):
    h, w = flow.shape[:2]
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    return cv2.remap(img, gx + flow[..., 0], gy + flow[..., 1], cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)


def interpolate(a, b, t):
    ga, gb = small_gray(a), small_gray(b)
    f01, f10 = dis.calc(ga, gb, None), dis.calc(gb, ga, None)
    ca = np.exp(-np.linalg.norm(f01 + remap(f10, f01), axis=2) / 2.0).astype(np.float32)
    cb = np.exp(-np.linalg.norm(f10 + remap(f01, f10), axis=2) / 2.0).astype(np.float32)
    ft0 = -(1 - t) * t * f01 + t * t * f10
    ft1 = (1 - t) * (1 - t) * f01 - t * (1 - t) * f10
    ca, cb = remap(ca, ft0) * (1 - t) + 1e-4, remap(cb, ft1) * t + 1e-4
    H, W = a.shape[:2]
    k = W / ga.shape[1]
    up = lambda f: cv2.resize(f, (W, H), interpolation=cv2.INTER_LINEAR) * k
    upw = lambda m: cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR)[..., None]
    wa, wb = remap(a, up(ft0)), remap(b, up(ft1))
    wA, wB = upw(ca), upw(cb)
    return np.clip((wa * wA + wb * wB) / (wA + wB + 1e-6), 0, 1)


def thumb(i):
    a = load(i)
    return cv2.resize(a, (270, round(a.shape[0] * 270 / a.shape[1])), interpolation=cv2.INTER_AREA)


# Shots as lists of (source index, time in seconds) of the frames to use.
bounds = [0] + [c - 1 for c in CUTS] + [len(files)]
shots = []
for s0, s1 in zip(bounds, bounds[1:]):
    idx = list(range(s0, s1))
    if os.environ.get('DEDUPE'):
        # A frame is a repeat when it barely changes while its neighbours move: generated repeats are not
        # bit-identical, so compare each frame's change with the motion around it.
        th = [thumb(i) for i in range(s0, s1)]
        d = [np.inf] + [np.abs(th[k] - th[k - 1]).mean() * 255 for k in range(1, len(th))]
        keep = [s0]
        for k in range(1, len(th)):
            around = max(d[k - 1] if k > 1 else 0, d[k + 1] if k + 1 < len(d) else 0)
            if not (d[k] < 1.2 and d[k] < 0.35 * around):
                keep.append(s0 + k)
        idx = keep
    t0, t1 = s0 / SRC_FPS, s1 / SRC_FPS
    # first real frame at the shot start, last one on the final output frame before the cut (no hold)
    step = (t1 - 1 / OUT_FPS - t0) / max(len(idx) - 1, 1)
    shots.append([(i, t0 + k * step) for k, i in enumerate(idx)] + [(None, t1)])
    print(f'shot {s0 + 1}-{s1}: {len(idx)} of {s1 - s0} frames used')

n_out = int(round(DUR * OUT_FPS))
for n in range(n_out):
    T = n / OUT_FPS
    shot = next((sh for sh in shots if T < sh[-1][1] - 1e-9), shots[-1])
    seq = shot[:-1]
    j = max(k for k, (_, tk) in enumerate(seq) if tk <= T + 1e-9) if T >= seq[0][1] else 0
    i, ti = seq[j]
    if j + 1 < len(seq):
        i2, ti2 = seq[j + 1]
        t = (T - ti) / (ti2 - ti)
    else:
        i2, t = i, 0.0
    if t < 0.05:
        out = load(i)
    elif t > 0.95:
        out = load(i2)
    else:
        out = interpolate(load(i), load(i2), float(t))
    cv2.imwrite(str(OUT / f'f{n + 1:04d}.png'), (out * 65535 + 0.5).astype(np.uint16))
print(f'{n_out} frames at {OUT_FPS} fps')
