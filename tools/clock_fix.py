"""Targeted fixes on the approved Seedance relight, nothing else touched:
1. The wall clock was turned into a glowing light. Inside a soft zone around the glow, rebuild the wall from the
   aligned source footage (real clock line art), tinted with the warm wash measured on the wall just outside the
   zone, so it reads as printed mural under the same ambient light.
2. The small blue light at the right of the monitor bank is recolored to the LED orange, keeping its brightness.
People are protected by a soft matte. Frames where nothing is detected are copied unchanged.

Usage: python tools/clock_fix.py <gen_frames_dir> <gen_fps> <src_frames_dir> <src_fps> <out_dir> <models_dir> <first_seconds>
(only frames at or after <first_seconds> are fixed, e.g. the shot after the cut)
"""
import shutil
import sys
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

GEN, GEN_FPS, SRC, SRC_FPS, OUT, MODELS = Path(sys.argv[1]), float(sys.argv[2]), Path(sys.argv[3]), float(sys.argv[4]), Path(sys.argv[5]), Path(sys.argv[6])
FROM = float(sys.argv[7])
OUT.mkdir(parents=True, exist_ok=True)
LED = np.array([40, 140, 255], np.float32)   # BGR of the under-desk LED strips in the approved render


def segmenter(name):
    opts = vision.ImageSegmenterOptions(base_options=BaseOptions(model_asset_path=str(MODELS / name)),
                                        output_confidence_masks=True, running_mode=vision.RunningMode.IMAGE)
    return vision.ImageSegmenter.create_from_options(opts)


MULTI, SELFIE = segmenter('selfie_multiclass_256x256.tflite'), segmenter('selfie_segmenter.tflite')
SIFT = cv2.SIFT_create(5000)


def person(bgr):
    h, w = bgr.shape[:2]
    img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    p1 = 1 - MULTI.segment(img).confidence_masks[0].numpy_view()
    p2 = SELFIE.segment(img).confidence_masks[0].numpy_view()
    p = np.maximum(cv2.resize(p1, (w, h)), cv2.resize(p2, (w, h)))
    p = np.clip((p - 0.15) / 0.35, 0, 1).astype(np.float32)
    return cv2.GaussianBlur(cv2.dilate(p, np.ones((9, 9), np.uint8)), (0, 0), 3)


def align(src, gen, bg):
    ka, da = SIFT.detectAndCompute(cv2.cvtColor(src, cv2.COLOR_BGR2GRAY), None)
    kb, db = SIFT.detectAndCompute(cv2.cvtColor(gen, cv2.COLOR_BGR2GRAY), bg)
    good = [m for m, n in cv2.BFMatcher().knnMatch(da, db, k=2) if m.distance < 0.75 * n.distance]
    if len(good) < 12:
        return None, 0
    a = np.float32([ka[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    b = np.float32([kb[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    h, inl = cv2.findHomography(a, b, cv2.RANSAC, 3.0)
    return h, int(inl.sum()) if inl is not None else 0


src_files = sorted(SRC.glob('f*.png'))
for k, gf in enumerate(sorted(GEN.glob('f*.png'))):
    if k / GEN_FPS < FROM:
        shutil.copy(gf, OUT / gf.name)
        continue
    full = cv2.imread(str(gf))
    FH, FW = full.shape[:2]
    sc = FW / 1080.0                       # detection runs at 1080 wide; the fix is applied at full resolution
    g = cv2.resize(full, (1080, round(FH / sc)), interpolation=cv2.INTER_AREA) if sc != 1 else full
    H, W = g.shape[:2]
    up = lambda m: cv2.resize(m, (FW, FH), interpolation=cv2.INTER_LINEAR) if sc != 1 else m
    hsv = cv2.cvtColor(g, cv2.COLOR_BGR2HSV)
    out = full.astype(np.float32)
    notes = []

    # 1. Clock glow: very bright, saturated orange in the upper-left of the frame.
    glow = ((hsv[..., 0] <= 25) & (hsv[..., 1] > 140) & (hsv[..., 2] > 215)).astype(np.uint8)
    glow[int(0.4 * H):, :] = 0
    glow[:, int(0.5 * W):] = 0
    glow = cv2.morphologyEx(glow, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    p = None
    if glow.sum() > 1500:
        zone = cv2.dilate(glow, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (121, 121)))
        zone = cv2.morphologyEx(zone, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (151, 151)))
        p = person(g)
        bg = ((p < 0.05) * 255).astype(np.uint8)
        t = k / GEN_FPS
        best = None
        for n in range(max(0, round(t * SRC_FPS) - 1), min(len(src_files), round(t * SRC_FPS) + 2)):
            hm, inl = align(cv2.imread(str(src_files[n])), g, bg)
            if hm is not None and (best is None or inl > best[1]):
                best = (hm, inl, n)
        if best and best[1] >= 25:
            src_img = cv2.imread(str(src_files[best[2]]))
            s_small = cv2.warpPerspective(src_img, best[0], (W, H), flags=cv2.INTER_CUBIC,
                                          borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
            # Warm wash on the wall just outside the zone: per-channel generated/source ratio, robust median.
            ring = (cv2.dilate(zone, np.ones((61, 61), np.uint8)) - zone).astype(bool) & (p < 0.05) & (s_small.max(2) > 60)
            if ring.sum() > 500:
                ratio = np.median(g.astype(np.float32)[ring] / np.maximum(s_small[ring], 1), axis=0)
                hfull = np.diag([sc, sc, 1.0]) @ best[0]
                s = cv2.warpPerspective(src_img, hfull, (FW, FH), flags=cv2.INTER_CUBIC,
                                        borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
                rebuilt = np.clip(s * ratio, 0, 255)
                z = up(cv2.GaussianBlur(zone.astype(np.float32), (0, 0), 25) * (1 - p))[..., None]
                out = out * (1 - z) + rebuilt * z
                notes.append(f'clock rebuilt from src f{best[2]:03d}')

    # 2. Blue practical at the right of the monitors: recolor to LED orange at the same brightness.
    blue = ((hsv[..., 0] > 95) & (hsv[..., 0] < 135) & (hsv[..., 1] > 120) & (hsv[..., 2] > 90)).astype(np.uint8)
    blue[:, : int(0.75 * W)] = 0
    blue = cv2.morphologyEx(blue, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    if blue.sum() > 150:
        m = cv2.GaussianBlur(cv2.dilate(blue, np.ones((25, 25), np.uint8)).astype(np.float32), (0, 0), 8)
        if p is not None:
            m = m * (1 - p)
        m = up(m)[..., None]
        lum = out.max(2, keepdims=True)
        out = out * (1 - m) + (lum / 255.0) * LED * m
        notes.append('blue light recolored')

    cv2.imwrite(str(OUT / gf.name), np.clip(out + 0.5, 0, 255).astype(np.uint8))
    if notes:
        print(f'{gf.name}: ' + ', '.join(notes))
