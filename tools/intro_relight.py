"""Intro fix-up: orange LED practicals behind the monitors and under the desk, plus a smoother first cut.

Compositing only, the people are never regenerated:
- A person matte (two MediaPipe segmenters, unioned, held across neighbouring frames, dilated)
  protects the presenter and the colleague; glow is never added on top of them.
- Glow guides (monitor-bank top edges, desk front edges) are drawn once per shot on its first frame
  and follow the camera with a homography tracked on background features only.
- The wide shot's dead moment (she settles before raising her hands) is sped up with frame
  blending, and the last frames of the wide shot push in toward her face so it flows into the cut.

Usage: python tools/intro_relight.py <frames_dir> <out_frames_dir> <models_dir>
Frames are f000.png ... (1080 x 1920). Shot ranges and guides below match "Intro.mov".
"""
import sys
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

SRC, OUT, MODELS = (Path(p) for p in sys.argv[1:4])
OUT.mkdir(parents=True, exist_ok=True)

W, H = 1080, 1920
ORANGE = np.array([30, 120, 255], np.float32) / 255  # BGR

# Shots: (first, last) frame indices. Frames 108-109 belong to the next shot and stay untouched.
SHOTS = {'wide': (0, 31), 'medium': (32, 107)}

# Guides in the first frame of each shot, full-resolution pixels.
GUIDES = {
    'wide': {
        'monitor_top': [[(100, 515), (360, 548), (600, 560), (850, 585)]],
        'desk_edge': [[(0, 972), (260, 978), (520, 986)]],
    },
    'medium': {
        'monitor_top': [[(60, 528), (400, 524)], [(780, 532), (1040, 526)]],
        'desk_edge': [[(100, 962), (330, 962)], [(930, 934), (1080, 930)]],
    },
}

# Retime of the wide shot: (source frame, speed). Speed 1 = normal; >1 skips through the dead moment.
WIDE_SPEED = [(0, 1.0), (13, 1.0), (16, 2.8), (23, 2.8), (26, 1.0), (31, 1.0)]
PUSH_FRAMES, PUSH_SCALE = 9, 1.07           # push-in over the last frames of the wide shot
PUSH_FROM, PUSH_TO = (370, 520), (470, 540)  # her face drifts toward where it sits after the cut


def segmenter(name):
    opts = vision.ImageSegmenterOptions(base_options=BaseOptions(model_asset_path=str(MODELS / name)),
                                        output_confidence_masks=True, running_mode=vision.RunningMode.IMAGE)
    return vision.ImageSegmenter.create_from_options(opts)


def person_masks(frames):
    multi, selfie = segmenter('selfie_multiclass_256x256.tflite'), segmenter('selfie_segmenter.tflite')
    raw = []
    for bgr in frames:
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        p1 = 1 - multi.segment(img).confidence_masks[0].numpy_view()
        p2 = selfie.segment(img).confidence_masks[0].numpy_view()
        p = np.maximum(cv2.resize(p1, (W, H)), cv2.resize(p2, (W, H)))
        raw.append(np.clip((p - 0.15) / 0.35, 0, 1).astype(np.float32))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (45, 45))
    out = []
    for i in range(len(raw)):
        m = np.max(raw[max(0, i - 2):i + 3], axis=0)          # hold through motion blur
        m = cv2.dilate(m, kernel)
        out.append(cv2.GaussianBlur(m, (0, 0), 9))
    return out


def track(frames, masks):
    """Cumulative homography from the shot's first frame to each frame, background only."""
    hs = [np.eye(3)]
    prev = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
    for i in range(1, len(frames)):
        cur = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY)
        bg = ((masks[i - 1] < 0.05) * 255).astype(np.uint8)
        pts = cv2.goodFeaturesToTrack(prev, 1500, 0.005, 7, mask=bg)
        rel = None
        if pts is not None and len(pts) > 40:
            nxt, st, _ = cv2.calcOpticalFlowPyrLK(prev, cur, pts, None, winSize=(31, 31), maxLevel=4)
            good = st.ravel() == 1
            if good.sum() > 40:
                rel, inl = cv2.findHomography(pts[good], nxt[good], cv2.RANSAC, 3.0)
                if rel is None or inl.sum() < 30:
                    rel = None
        hs.append((rel if rel is not None else np.eye(3)) @ hs[-1])
        prev = cur
    return hs


def warp_lines(lines, h):
    return [cv2.perspectiveTransform(np.array(l, np.float32).reshape(-1, 1, 2), h).reshape(-1, 2) for l in lines]


def side_mask(lines, above):
    """Soft mask of everything above (or below) the guide lines, limited to their x span."""
    m = np.zeros((H, W), np.float32)
    for l in lines:
        edge = [tuple(map(int, p)) for p in l]
        if above:
            poly = [(edge[0][0], -400)] + edge + [(edge[-1][0], -400)]
        else:
            poly = [(edge[0][0], H + 400)] + edge + [(edge[-1][0], H + 400)]
        cv2.fillPoly(m, [np.array(poly, np.int32)], 1.0)
    return cv2.GaussianBlur(m, (0, 0), 6)


def glow_layer(guides, h):
    scale = float(np.sqrt(abs(np.linalg.det(h[:2, :2]))))
    glow = np.zeros((H, W), np.float32)

    # Bias light on the wall above the monitor banks.
    mon = warp_lines(guides['monitor_top'], h)
    layer = np.zeros((H, W), np.float32)
    for l in mon:
        cv2.polylines(layer, [(l + [0, -14 * scale]).astype(np.int32)], False, 1.0, int(26 * scale))
    wall = cv2.GaussianBlur(layer, (0, 0), 55 * scale) * 2.6 + cv2.GaussianBlur(layer, (0, 0), 14 * scale) * 0.55
    glow += wall * side_mask(mon, above=True)

    # LED strip under the desk front edge, spilling onto the floor and partition.
    desk = warp_lines(guides['desk_edge'], h)
    strip, spill = np.zeros((H, W), np.float32), np.zeros((H, W), np.float32)
    for l in desk:
        cv2.polylines(strip, [(l + [0, 12 * scale]).astype(np.int32)], False, 1.0, max(3, int(7 * scale)))
        cv2.polylines(spill, [(l + [0, 90 * scale]).astype(np.int32)], False, 1.0, int(70 * scale))
    under = cv2.GaussianBlur(strip, (0, 0), 3 * scale) * 0.9 + cv2.GaussianBlur(spill, (0, 0), 70 * scale) * 1.6
    glow += under * side_mask(desk, above=False)
    return np.clip(glow, 0, 1)


def light_shot(name, first, last):
    frames = [cv2.imread(str(SRC / f'f{n:03d}.png')) for n in range(first, last + 1)]
    masks = person_masks(frames)
    hs = track(frames, masks)
    out = []
    for bgr, m, h in zip(frames, masks, hs):
        g = glow_layer(GUIDES[name], h) * (1 - m)
        f = bgr.astype(np.float32) / 255
        light = g[..., None] * ORANGE
        f = 1 - (1 - f) * (1 - light)                     # screen blend
        f = f * (1 - m[..., None]) + bgr.astype(np.float32) / 255 * m[..., None]  # people stay original
        out.append(np.clip(f * 255 + 0.5, 0, 255).astype(np.uint8))
    return out, masks


def retime(frames, keys):
    """Variable speed with frame blending; returns new frame list."""
    def speed(t):
        for (a, sa), (b, sb) in zip(keys, keys[1:]):
            if t <= b:
                u = (t - a) / (b - a)
                return sa + (sb - sa) * u * u * (3 - 2 * u)
        return keys[-1][1]
    out, t = [], 0.0
    while t <= len(frames) - 1:
        s = speed(t)
        lo, hi = int(t), min(len(frames) - 1, int(t + s - 1e-6))
        out.append(np.mean([frames[i].astype(np.float32) for i in range(lo, hi + 1)], axis=0).astype(np.uint8))
        t += s
    return out


def push(frames, n, scale, src_pt, dst_pt):
    out = list(frames)
    for k in range(n):
        u = (k + 1) / n
        e = u * u * (3 - 2 * u)
        s = 1 + (scale - 1) * e
        tx = src_pt[0] + (dst_pt[0] - src_pt[0]) * e
        ty = src_pt[1] + (dst_pt[1] - src_pt[1]) * e
        # Scale about the face, then move the face toward its post-cut position.
        m = np.array([[s, 0, tx - s * src_pt[0]], [0, s, ty - s * src_pt[1]]], np.float32)
        i = len(frames) - n + k
        out[i] = cv2.warpAffine(frames[i], m, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
    return out


wide, wide_masks = light_shot('wide', *SHOTS['wide'])
medium, _ = light_shot('medium', *SHOTS['medium'])
wide = push(retime(wide, WIDE_SPEED), PUSH_FRAMES, PUSH_SCALE, PUSH_FROM, PUSH_TO)
tail = [cv2.imread(str(SRC / f'f{n:03d}.png')) for n in (108, 109)]

final = wide + medium + tail
for i, f in enumerate(final):
    cv2.imwrite(str(OUT / f'o{i:03d}.png'), f)
print(f'wide shot {SHOTS["wide"][1] + 1} -> {len(wide)} frames; total {len(final)} frames')
