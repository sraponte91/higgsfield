import numpy as np
LUMA = np.array([0.2126, 0.7152, 0.0722])
M = np.array([[1.6269474, -0.5401385, -0.0868089], [-0.1785155, 1.4179409, -0.2394254], [-0.0444361, -0.1959199, 1.2403560]])
def slog3_to_lin(x):
    c = x * 1023
    return np.where(c >= 171.2102946929, (10 ** ((c - 420) / 261.5)) * 0.19 - 0.01, (c - 95) * 0.01125 / (171.2102946929 - 95))
def aces(x):
    x = np.maximum(x, 0); return np.clip(x * (2.51 * x + 0.03) / (x * (2.43 * x + 0.59) + 0.14), 0, 1)
def oetf(y): return np.clip(np.where(y < 0.018, 4.5 * y, 1.099 * np.maximum(y, 0) ** 0.45 - 0.099), 0, 1)
P = dict(ev=-0.36, gain=(1.22, 1.0, 0.95), contrast=1.10, sat=0.92)
def grade_lin(lin, p=P):
    l = lin @ LUMA
    w = np.clip((l - 0.03) / 0.25, 0, 1)[..., None]          # warm the bright surfaces (wall), keep shadows neutral
    lin = lin * (1 + w * (np.array(p['gain']) - 1))
    v = oetf(aces(lin * 2 ** p['ev'] * 0.8))
    v = np.clip(0.42 + (v - 0.42) * p['contrast'], 0, 1)
    lv = (v @ LUMA)[..., None]
    return np.clip(lv + (v - lv) * p['sat'], 0, 1)
def grade_code(x, p=P):
    return grade_lin(slog3_to_lin(x) @ M.T, p)
