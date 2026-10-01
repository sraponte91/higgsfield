"""Post-fix a Seedance relight without spending credits: put the original walls back and recolor the LED light.

For each generated frame:
1. Find the matching source frame (nearest in time, best match) and align it to the generated frame with a
   SIFT + RANSAC homography on background features.
2. Only the under-desk zones (orange partitions and dark floor/desk undersides in the source) keep the
   added LED light, swapped from orange to the new color (generated minus source, warm excess, smoothed).
3. The rest of the background (walls, ceiling, clock, desks, monitors) is restored from the aligned source,
   so no light lands on the walls.
4. People keep the generated pixels (soft matte), exactly as Seedance rendered them, except a thin band at
   the silhouette where the old wall glow's warm rim is pulled back to the source color.

Usage: python tools/seedance_recolor.py <gen_frames_dir> <gen_fps> <src_frames_dir> <src_fps> <out_dir> <models_dir> [last_frame]
"""
import sys
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

GEN, GEN_FPS, SRC, SRC_FPS, OUT, MODELS = Path(sys.argv[1]), float(sys.argv[2]), Path(sys.argv[3]), float(sys.argv[4]), Path(sys.argv[5]), Path(sys.argv[6])
LAST = int(sys.argv[7]) if len(sys.argv) > 7 else None
OUT.mkdir(parents=True, exist_ok=True)

ORANGE = np.array([0.16, 0.52, 1.0], np.float32)   # BGR, red = 1: the generated LED color
BLUE = np.array([1.0, 0.42, 0.08], np.float32)     # BGR, blue = 1: the new LED color


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
    src_pts = np.float32([ka[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst_pts = np.float32([kb[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    h, inl = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 3.0)
    return h, int(inl.sum()) if inl is not None else 0


gen_files = sorted(GEN.glob('f*.png'))[:LAST]
src_files = sorted(SRC.glob('f*.png'))
src_cache = {}


def src(n):
    if n not in src_cache:
        src_cache[n] = cv2.imread(str(src_files[n]))
    return src_cache[n]


for k, gf in enumerate(gen_files):
    g = cv2.imread(str(gf))
    h_, w_ = g.shape[:2]
    p = person(g)
    bg = ((p < 0.05) * 255).astype(np.uint8)
    # Matching source frame: nearest in time, refined by best alignment (motion-blurred frames can drift).
    t = k / GEN_FPS
    best = None
    for n in range(max(0, round(t * SRC_FPS) - 1), min(len(src_files), round(t * SRC_FPS) + 2)):
        hm, inl = align(src(n), g, bg)
        if hm is not None and (best is None or inl > best[1]):
            best = (hm, inl, n)
    if best is None or best[1] < 25:
        cv2.imwrite(str(OUT / gf.name), g)
        print(f'{gf.name}: no reliable alignment, kept as generated')
        continue
    hm, inl, n = best
    s = cv2.warpPerspective(src(n), hm, (w_, h_), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    # Only the under-desk zones keep (recolored) LED light: the orange partitions and the dark floor/desk
    # undersides in the source. Everything else in the background (walls, ceiling, clock, desks, monitors)
    # is restored from the source, so no light lands on the walls.
    hsv = cv2.cvtColor(s, cv2.COLOR_BGR2HSV)
    partition = ((hsv[..., 0] <= 22) | (hsv[..., 0] >= 170)) & (hsv[..., 1] > 90) & (hsv[..., 2] > 40)
    dark = hsv[..., 2] < 85
    keep = (partition | dark).astype(np.uint8)
    keep = cv2.morphologyEx(keep, cv2.MORPH_OPEN, np.ones((17, 17), np.uint8))   # drop small red mural details
    keep = cv2.morphologyEx(keep, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    wall = 1 - cv2.GaussianBlur(keep.astype(np.float32), (0, 0), 4)

    # Added warm light elsewhere, swapped to the new color.
    d = g.astype(np.float32) - s.astype(np.float32)
    warm = np.clip(d[..., 2] - d[..., 0], 0, None)
    light = cv2.GaussianBlur(warm, (0, 0), 10) / (1 - ORANGE[0])        # approx. intensity on the red channel
    recolored = g.astype(np.float32) + light[..., None] * (BLUE - ORANGE)

    bgd = s.astype(np.float32) * wall[..., None] + recolored * (1 - wall[..., None])
    # The old wall glow left a warm rim on hair and shoulder edges: in a thin band at the silhouette, pull the
    # low-frequency color back to the source's while keeping the generated detail. The face is not in the band.
    solid = cv2.erode((p > 0.5).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (41, 41)))
    band = cv2.GaussianBlur(((p > 0.05) & (solid == 0)).astype(np.float32), (0, 0), 6)[..., None]
    g32, s32 = g.astype(np.float32), s.astype(np.float32)
    ratio = np.clip((cv2.GaussianBlur(s32, (0, 0), 12) + 4) / (cv2.GaussianBlur(g32, (0, 0), 12) + 4), 0.6, 1.4)
    person_px = g32 * (1 - band) + g32 * ratio * band
    out = person_px * p[..., None] + bgd * (1 - p[..., None])
    cv2.imwrite(str(OUT / gf.name), np.clip(out + 0.5, 0, 255).astype(np.uint8))
    print(f'{gf.name}: src f{n:03d}, {inl} inliers')
