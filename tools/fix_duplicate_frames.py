"""Replace duplicated frames in a range with motion-interpolated in-between frames.

Real frames stay exactly where they are; only frames identical to their predecessor are rebuilt,
so timing, action and cuts are unchanged and the motion becomes fluid.

Interpolation: dense optical flow (OpenCV DIS) both ways between the neighbouring real frames,
intermediate flows estimated for t = 0.5, both neighbours backward-warped and blended with
weights from forward/backward flow consistency (handles occlusions at moving edges).
A duplicate with no real frame after it in the range (e.g. right before a cut) is extrapolated
by continuing the previous motion half a step.

Usage: python tools/fix_duplicate_frames.py <frames_dir> <out_dir> <first> <last>
Frames are named f000.png ...; frames outside [first, last] are copied unchanged.
"""
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
FIRST, LAST = int(sys.argv[3]), int(sys.argv[4])
OUT.mkdir(parents=True, exist_ok=True)

frames = sorted(SRC.glob('f*.png'))
img = {int(p.stem[1:]): cv2.imread(str(p)) for p in frames}
dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
dis.setFinestScale(1)


def gray(a):
    return cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)


def flow(a, b):
    return dis.calc(gray(a), gray(b), None)


def remap(a, f):
    h, w = f.shape[:2]
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    return cv2.remap(a, gx + f[..., 0], gy + f[..., 1], cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)


def interpolate(a, b, t=0.5):
    f01, f10 = flow(a, b), flow(b, a)
    ft0 = -(1 - t) * t * f01 + t * t * f10
    ft1 = (1 - t) * (1 - t) * f01 - t * (1 - t) * f10
    wa, wb = remap(a, ft0).astype(np.float32), remap(b, ft1).astype(np.float32)
    # Consistency: how well each side's flow round-trips; pixels that don't are likely occluded there.
    ca = np.exp(-np.linalg.norm(f01 + remap(f10, f01), axis=2) / 4.0).astype(np.float32)
    cb = np.exp(-np.linalg.norm(f10 + remap(f01, f10), axis=2) / 4.0).astype(np.float32)
    ca = remap(ca, ft0)[..., None] * (1 - t) + 1e-4   # sample at the in-between pixel positions
    cb = remap(cb, ft1)[..., None] * t + 1e-4
    return np.clip((wa * ca + wb * cb) / (ca + cb), 0, 255).astype(np.uint8)


def extrapolate(prev, cur, t=0.5):
    """Continue the motion prev -> cur by t steps past cur."""
    back = flow(cur, prev)          # where each pixel of `cur` was in `prev`
    return remap(cur, t * back)


def is_dup(n):
    return n - 1 in img and np.mean(np.abs(gray(img[n]).astype(np.int16) - gray(img[n - 1]))) < 0.6


fixed = []
for n in sorted(img):
    out = img[n]
    if FIRST < n <= LAST and is_dup(n):
        prev_real = n - 1
        nxt = next((m for m in range(n + 1, LAST + 1) if not is_dup(m)), None)
        if nxt is not None:
            out = interpolate(img[prev_real], img[nxt], (n - prev_real) / (nxt - prev_real))
        else:
            before = max(m for m in range(FIRST, prev_real) if not is_dup(m))
            out = extrapolate(img[before], img[prev_real], (n - prev_real) / (prev_real - before))
        fixed.append(n)
    cv2.imwrite(str(OUT / f'f{n:03d}.png'), out)

print(f'rebuilt {len(fixed)} duplicate frames: {fixed}')
