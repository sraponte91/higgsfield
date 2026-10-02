"""Remove stutter at the native frame rate: rebuild only the frames that repeat the previous one.

Real frames are copied untouched. A frame counts as a repeat when it barely changes while the motion around it
does (generated repeats are not bit-identical). Each run of repeats is rebuilt from the real frames on either
side with optical flow (see retime_flow.interpolate), spaced evenly between them. Never across a cut.

Usage: python tools/rebuild_repeats.py <frames_dir> <out_dir> [cut_frame ...]   (cut_frame = 1-based first frame of a shot)
"""
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
CUTS = sorted(int(c) for c in sys.argv[3:])
OUT.mkdir(parents=True, exist_ok=True)
files = sorted(SRC.glob('f*.png'))
dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)


def load(i):
    a = cv2.imread(str(files[i]), cv2.IMREAD_UNCHANGED)
    return a.astype(np.float32) / (65535.0 if a.dtype == np.uint16 else 255.0)


def small_gray(a):
    s = cv2.resize(a, (1080, round(a.shape[0] * 1080 / a.shape[1])), interpolation=cv2.INTER_AREA)
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


th = [cv2.resize(load(i), (270, 480), interpolation=cv2.INTER_AREA) for i in range(len(files))]
starts = {0} | {c - 1 for c in CUTS}
d = [np.inf if i in starts else np.abs(th[i] - th[i - 1]).mean() * 255 for i in range(len(files))]
repeat = []
for i in range(len(files)):
    if i in starts:
        repeat.append(False); continue
    nxt = d[i + 1] if i + 1 < len(files) and (i + 1) not in starts else 0
    prv = d[i - 1] if (i - 1) not in starts and np.isfinite(d[i - 1]) else 0
    repeat.append(d[i] < 1.2 and d[i] < 0.35 * max(prv, nxt))

rebuilt = []
for i in range(len(files)):
    if not repeat[i]:
        shutil.copy(files[i], OUT / files[i].name)
        continue
    a = i - 1
    while repeat[a]:
        a -= 1
    b = i + 1
    while b < len(files) and repeat[b] and b not in starts:
        b += 1
    if b >= len(files) or b in starts:          # repeat right before a cut: keep it
        shutil.copy(files[i], OUT / files[i].name)
        continue
    out = interpolate(load(a), load(b), (i - a) / (b - a))
    cv2.imwrite(str(OUT / files[i].name), (out * 65535 + 0.5).astype(np.uint16))
    rebuilt.append(i + 1)
print(f'rebuilt {len(rebuilt)} of {len(files)} frames: {rebuilt}')
