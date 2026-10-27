"""Place a skin onto the reference rig: find the skull and derive BR->skin similarity transforms."""
from functools import lru_cache

import cv2
import numpy as np

from . import reference as ref


def skull_features(rgba):
    """Find the skull face: a light region whose convex hull holds two large dark eye sockets."""
    al = rgba[..., 3]
    hsv = cv2.cvtColor(np.ascontiguousarray(rgba[..., :3]), cv2.COLOR_BGR2HSV)
    light = ((hsv[..., 2] > 165) & (hsv[..., 1] < 70) & (al > 200)).astype(np.uint8)
    darkish = (hsv[..., 2] < 140) & (al > 200)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(light, connectivity=4)
    H, W = light.shape
    best = None
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < 0.002 * H * W:
            continue
        comp = (lab == i).astype(np.uint8)
        cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        hull = np.zeros_like(comp)
        cv2.fillConvexPoly(hull, cv2.convexHull(np.concatenate(cnts)), 1)
        holes = ((hull > 0) & (comp == 0) & darkish).astype(np.uint8)
        holes = cv2.morphologyEx(holes, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        hn, _, hs, hc = cv2.connectedComponentsWithStats(holes, connectivity=8)
        hull_area = int(hull.sum())
        big = [(hs[j, 4], hc[j], hs[j]) for j in range(1, hn) if hs[j, 4] > 0.03 * hull_area]
        if len(big) < 2:
            continue
        big.sort(key=lambda t: -t[0])
        e1, e2 = big[0], big[1]
        if abs(e1[1][1] - e2[1][1]) > 0.3 * h or abs(e1[1][0] - e2[1][0]) < 0.25 * w:
            continue
        if (e1[0] + e2[0]) / hull_area < 0.12:
            continue
        score = e1[0] + e2[0]
        if best is None or score > best["score"]:
            eyes = sorted([e1, e2], key=lambda t: t[1][0])
            best = dict(score=int(score), bbox=(int(x), int(y), int(w), int(h)),
                        eyes=[eyes[0][1].tolist(), eyes[1][1].tolist()],
                        eye_boxes=[eyes[0][2][:4].tolist(), eyes[1][2][:4].tolist()],
                        mask=hull.astype(bool))
    return best


@lru_cache(maxsize=1)
def ref_skull():
    return skull_features(ref.ref_image())


def sim(s, tx, ty):
    return np.array([[s, 0.0, tx], [0.0, s, ty]])


def from_skull(fs):
    fb = ref_skull()
    s = float(np.median([fs["bbox"][2] / fb["bbox"][2],
                         fs["eye_boxes"][0][2] / fb["eye_boxes"][0][2],
                         fs["eye_boxes"][0][3] / fb["eye_boxes"][0][3]]))
    t = np.array(fs["eyes"][0]) - s * np.array(fb["eyes"][0])
    return sim(s, t[0], t[1])


def from_silhouette(rgba):
    """Fallback when no skull is found: match the alpha bounding box heights."""
    ra = ref.ref_image()
    ys, xs = np.nonzero(ra[..., 3] > 0)
    ys2, xs2 = np.nonzero(rgba[..., 3] > 0)
    s = (ys2.max() - ys2.min()) / (ys.max() - ys.min())
    t = np.array([xs2.min(), ys2.min()]) - s * np.array([xs.min(), ys.min()])
    return sim(s, t[0], t[1])


def apply(S, p):
    return S[:, :2] @ np.asarray(p, float) + S[:, 2]


def warp_labels(S, shape):
    return cv2.warpAffine(ref.ref_labels(), S, (shape[1], shape[0]), flags=cv2.INTER_NEAREST, borderValue=0)
