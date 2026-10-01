"""Transfer AI-designed lighting from a relit key frame onto real footage, people untouched.

For each shot:
1. Align the AI-relit key frame to the real key frame (SIFT + RANSAC homography, background only).
2. Extract the added light: per-pixel brightening where the image got warmer (R up more than B),
   lightly smoothed. The area the people cover in the key frame is inpainted from its surroundings,
   so no light "ghost" of the person is left behind when they move.
3. Track the camera through the shot (homography on background features) and carry the light layer
   onto every frame.
4. Add it to the background only: a person matte (two MediaPipe segmenters, unioned, held across
   neighbouring frames, dilated) keeps the people's pixels exactly original.

Usage: python tools/ai_light_composite.py <frames_dir> <out_dir> <models_dir> <shot_spec> [<shot_spec> ...]
shot_spec = first:last:key_frame_index:relit_image[:gain[:fast]]   e.g. 0:31:0:lit_wide.png:1.3:fast
("fast" = confidence-as-transparency matte, for motion-blurred shots)
Frames are f000.png ... ; frames not covered by a shot are copied unchanged.
"""
import shutil
import sys
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

SRC, OUT, MODELS = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
SHOTS = []
for spec in sys.argv[4:]:
    parts = spec.split(':')
    SHOTS.append((int(parts[0]), int(parts[1]), int(parts[2]), parts[3], float(parts[4]) if len(parts) > 4 else 1.0,
                  len(parts) > 5 and parts[5] == 'fast'))
OUT.mkdir(parents=True, exist_ok=True)


def load(n):
    return cv2.imread(str(SRC / f'f{n:03d}.png'))


def segmenter(name):
    opts = vision.ImageSegmenterOptions(base_options=BaseOptions(model_asset_path=str(MODELS / name)),
                                        output_confidence_masks=True, running_mode=vision.RunningMode.IMAGE)
    return vision.ImageSegmenter.create_from_options(opts)


MULTI, SELFIE = segmenter('selfie_multiclass_256x256.tflite'), segmenter('selfie_segmenter.tflite')


def raw_person(bgr):
    h, w = bgr.shape[:2]
    img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    p1 = 1 - MULTI.segment(img).confidence_masks[0].numpy_view()
    p2 = SELFIE.segment(img).confidence_masks[0].numpy_view()
    p = np.maximum(cv2.resize(p1, (w, h)), cv2.resize(p2, (w, h)))
    return np.clip((p - 0.15) / 0.35, 0, 1).astype(np.float32)


def person_masks(frames, hold=1, grow=13):
    """Soft person matte per frame. `hold` keeps the matte over neighbouring frames (safer on slow shots)."""
    raw = [raw_person(f) for f in frames]
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (grow, grow))
    return [cv2.GaussianBlur(cv2.dilate(np.max(raw[max(0, i - hold):i + hold + 1], axis=0), kernel), (0, 0), 3)
            for i in range(len(raw))]


def blur_masks(frames):
    """Matte for fast, motion-blurred shots: the segmenter's confidence is used as transparency, so the
    lit wall shows through the see-through blur trail (as it would in camera) instead of leaving an
    unlit halo; solid parts of the person (confidence ~1) stay exactly original."""
    out, cores = [], []
    for f in frames:
        h, w = f.shape[:2]
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
        p1 = 1 - MULTI.segment(img).confidence_masks[0].numpy_view()
        p2 = SELFIE.segment(img).confidence_masks[0].numpy_view()
        p1, p2 = cv2.resize(p1, (w, h)), cv2.resize(p2, (w, h))
        # The multiclass model grades the blur trail as partly transparent; the selfie model calls it solid.
        m = np.clip((p1 - 0.25) / 0.55, 0, 1).astype(np.float32)
        both = cv2.dilate(((p1 > 0.85) & (p2 > 0.85)).astype(np.uint8), np.ones((7, 7), np.uint8))
        core = cv2.erode((p2 > 0.85).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (45, 45)))
        solid = cv2.GaussianBlur((both | core).astype(np.float32), (0, 0), 4)   # body interior stays solid
        out.append(cv2.GaussianBlur(np.maximum(m, solid), (0, 0), 2))
        face = cv2.resize(MULTI.segment(img).confidence_masks[3].numpy_view(), (w, h)) > 0.3
        core = core | cv2.dilate(face.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
        cores.append(cv2.GaussianBlur(core.astype(np.float32), (0, 0), 4))   # never see-through
    return out, cores


def track(frames, masks, key):
    """Homographies mapping the key frame's pixels into every frame of the shot."""
    def rel(a, b, m):
        ga, gb = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY), cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
        pts = cv2.goodFeaturesToTrack(ga, 1500, 0.005, 7, mask=((m < 0.05) * 255).astype(np.uint8))
        if pts is None or len(pts) < 40:
            return np.eye(3)
        nxt, st, _ = cv2.calcOpticalFlowPyrLK(ga, gb, pts, None, winSize=(31, 31), maxLevel=4)
        good = st.ravel() == 1
        if good.sum() < 40:
            return np.eye(3)
        h, inl = cv2.findHomography(pts[good], nxt[good], cv2.RANSAC, 3.0)
        return h if h is not None and inl.sum() >= 30 else np.eye(3)

    hs = [None] * len(frames)
    hs[key] = np.eye(3)
    for i in range(key + 1, len(frames)):
        hs[i] = rel(frames[i - 1], frames[i], masks[i - 1]) @ hs[i - 1]
    for i in range(key - 1, -1, -1):
        hs[i] = rel(frames[i + 1], frames[i], masks[i + 1]) @ hs[i + 1]
    return hs


def align(lit, real, mask):
    """Warp the AI frame onto the real frame's geometry using background features."""
    lit = cv2.resize(lit, (real.shape[1], real.shape[0]), interpolation=cv2.INTER_AREA)
    sift = cv2.SIFT_create(6000)
    bg = ((mask < 0.05) * 255).astype(np.uint8)
    ka, da = sift.detectAndCompute(cv2.cvtColor(lit, cv2.COLOR_BGR2GRAY), None)
    kb, db = sift.detectAndCompute(cv2.cvtColor(real, cv2.COLOR_BGR2GRAY), bg)
    matches = cv2.BFMatcher().knnMatch(da, db, k=2)
    good = [m for m, n in matches if m.distance < 0.75 * n.distance]
    src = np.float32([ka[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kb[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    h, inl = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
    warped = cv2.warpPerspective(lit, h, (real.shape[1], real.shape[0]), flags=cv2.INTER_CUBIC)
    valid = cv2.warpPerspective(np.ones(lit.shape[:2], np.float32), h, (real.shape[1], real.shape[0]))
    print(f'  aligned AI frame: {int(inl.sum())} inlier matches of {len(good)}')
    return warped, valid


LED_ORANGE = np.array([0.16, 0.52, 1.0], np.float32)  # BGR tint of a warm orange LED, red channel = 1


def light_layer(lit_aligned, valid, real, key_mask, ai_mask):
    """Intensity of the added warm light (from the red-channel gain), coloured as LED orange."""
    d = lit_aligned.astype(np.float32) - real.astype(np.float32)
    warm = d[..., 2] - d[..., 0]                                  # R gain minus B gain
    inside = cv2.erode((valid > 0.99).astype(np.uint8), np.ones((15, 15), np.uint8))
    weight = np.clip((warm - 4) / 22, 0, 1) * inside
    intensity = cv2.GaussianBlur(np.maximum(d[..., 2], 0) * weight, (0, 0), 4)
    # Fill the light behind where the people stood, and wherever the AI frame didn't cover the real
    # frame, from the surrounding light (at quarter resolution; the light is smooth anyway).
    # The AI may also have moved the people slightly, so fill where they are in either image.
    people = ((key_mask > 0.05) | (ai_mask > 0.05)).astype(np.uint8)
    hole = cv2.dilate(people, np.ones((41, 41), np.uint8)) | (1 - inside)
    h, w = intensity.shape
    small = cv2.resize(np.clip(intensity, 0, 255).astype(np.uint8), (w // 4, h // 4), interpolation=cv2.INTER_AREA)
    small_hole = (cv2.resize(hole, (w // 4, h // 4), interpolation=cv2.INTER_NEAREST) > 0).astype(np.uint8) * 255
    filled = cv2.inpaint(small, small_hole, 15, cv2.INPAINT_TELEA)
    filled = cv2.resize(filled.astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
    feather = cv2.GaussianBlur(hole.astype(np.float32), (0, 0), 25)
    intensity = filled * np.maximum(hole, feather) + intensity * (1 - np.maximum(hole, feather))
    intensity = cv2.GaussianBlur(intensity, (0, 0), 12)
    return intensity[..., None] * LED_ORANGE


def see_through(frames, masks, hs, i, core):
    """Refine a fast-shot matte: where a 'person' pixel matches the clean background behind it (built
    from neighbouring frames, camera-tracked), it is see-through motion blur, so the lit wall should
    show. Pixels that differ from the background (the person herself) keep full protection; tracking
    errors only make pixels differ, so they fail safe."""
    h, w = frames[i].shape[:2]
    plates, wts = [], []
    for j in range(len(frames)):
        if 3 <= abs(j - i) <= 12:
            hj = hs[i] @ np.linalg.inv(hs[j])
            plates.append(cv2.warpPerspective(frames[j], hj, (w, h)).astype(np.float32))
            wts.append(cv2.warpPerspective(masks[j], hj, (w, h), borderValue=1.0) < 0.1)
    if not plates:
        return masks[i]
    plates, wts = np.stack(plates), np.stack(wts)
    n = wts.sum(0)
    plate = np.where(n[..., None] > 0, (plates * wts[..., None]).sum(0) / np.maximum(n, 1)[..., None], frames[i])
    diff = cv2.GaussianBlur(np.abs(frames[i].astype(np.float32) - plate).max(2), (0, 0), 2)
    person = np.clip((diff - 16) / 30, 0, 1) * (n > 0) + (n == 0)
    person = cv2.GaussianBlur(cv2.dilate(person, np.ones((5, 5), np.uint8)), (0, 0), 3)
    return np.maximum(masks[i] * person, core[i])


covered = set()
for first, last, key_n, lit_path, gain, fast in SHOTS:
    print(f'shot {first}-{last} (key frame {key_n}{", fast-motion matte" if fast else ""})')
    frames = [load(n) for n in range(first, last + 1)]
    masks, cores = blur_masks(frames) if fast else (person_masks(frames), None)
    key = key_n - first
    lit_aligned, valid = align(cv2.imread(lit_path), frames[key], masks[key])
    ai_mask = person_masks([lit_aligned], hold=0)[0]
    layer = light_layer(lit_aligned, valid, frames[key], masks[key], ai_mask)
    hs = track(frames, masks, key)
    if fast:
        masks = [see_through(frames, masks, hs, i, cores) for i in range(len(frames))]
    for i, (f, m, h) in enumerate(zip(frames, masks, hs)):
        light = cv2.warpPerspective(layer, h, (f.shape[1], f.shape[0]), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        if fast:   # soft falloff toward the silhouette: any leftover blur edge reads as a soft shadow
            light = light * (1 - 0.6 * cv2.GaussianBlur(m, (0, 0), 35))[..., None]
        # Light scales with how bright the surface is (dark chairs pick up a little, walls a lot).
        albedo = np.clip(cv2.GaussianBlur(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32), (0, 0), 3) / 150, 0.3, 1.15)
        out = f.astype(np.float32) + gain * light * albedo[..., None] * (1 - m[..., None])
        out = out * (1 - m[..., None]) + f.astype(np.float32) * m[..., None]      # people stay original
        cv2.imwrite(str(OUT / f'f{first + i:03d}.png'), np.clip(out + 0.5, 0, 255).astype(np.uint8))
        covered.add(first + i)

for p in sorted(SRC.glob('f*.png')):
    if int(p.stem[1:]) not in covered:
        shutil.copy(p, OUT / p.name)
print(f'lit {len(covered)} frames')
