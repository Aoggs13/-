"""Black reaper reference: rig, idle_6 pose image and its part labels."""
import json
import os
from functools import lru_cache

import cv2
import numpy as np

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
LABELS = ["bg", "head", "body", "back_hand", "front_hand", "handle", "blade"]
L = {k: i for i, k in enumerate(LABELS)}


@lru_cache(maxsize=1)
def rig():
    with open(os.path.join(ASSETS, "rig.json")) as f:
        return json.load(f)


@lru_cache(maxsize=1)
def ref_image():
    return cv2.imread(os.path.join(ASSETS, "reference_idle.png"), cv2.IMREAD_UNCHANGED)


@lru_cache(maxsize=1)
def ref_labels():
    return cv2.imread(os.path.join(ASSETS, "reference_labels.png"), cv2.IMREAD_GRAYSCALE)


def ref_mask(*names):
    lab = ref_labels()
    m = np.zeros(lab.shape, bool)
    for n in names:
        m |= lab == L[n]
    return m


def ref_center(name):
    ys, xs = np.nonzero(ref_mask(name))
    return np.array([xs.mean(), ys.mean()])
