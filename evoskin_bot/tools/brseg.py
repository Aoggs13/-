import cv2, numpy as np
def load(p): return cv2.imread(p, cv2.IMREAD_UNCHANGED)
def classes(a):
    b,g,r,al = [a[...,i].astype(int) for i in range(4)]
    fg = al > 0
    mx = np.maximum(np.maximum(r,g),b); mn = np.minimum(np.minimum(r,g),b)
    wood = fg & (r-b > 25) & (r > 60)
    darkbrown = fg & (r-b > 8) & (r-b <= 25) & (mx < 110)
    grey = fg & (mx-mn < 14)
    white = grey & (mx >= 150)
    dark = grey & (mx >= 40) & (mx < 150)
    ink = fg & (mx < 40)
    return dict(fg=fg, wood=wood, darkbrown=darkbrown, white=white, dark=dark, ink=ink)
def dil(m, r):
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*r+1, 2*r+1))
    return cv2.dilate(m.astype(np.uint8), k).astype(bool)
def ref_parts(a):
    """Part masks for black reaper idle_6 (reference pose)."""
    c = classes(a); H,W = c['fg'].shape
    yy,xx = np.mgrid[0:H,0:W]
    fg = c['fg']
    woodish = c['wood'] | c['darkbrown']
    handle = fg & dil(woodish, 2) & ~(c['white'] & ~dil(woodish, 1))
    # blade: everything right of x=266 that is not handle
    blade = fg & (xx >= 266) & ~handle
    sc = handle | blade
    fh = fg & ~sc & (xx >= 213) & (xx <= 240) & (yy >= 175) & (yy <= 205)
    bh = fg & (xx >= 134) & (xx <= 163) & (yy >= 184) & (yy <= 214) & (c['white'] | c['ink'])
    skull = c['white'] & (yy < 160) & (xx > 145) & (xx < 245)
    head = fg & ~sc & (yy < 160)
    body = fg & ~sc & ~fh & ~bh & ~head
    return dict(handle=handle, blade=blade, scythe=sc, front_hand=fh, back_hand=bh, head=head, skull=skull, body=body)
