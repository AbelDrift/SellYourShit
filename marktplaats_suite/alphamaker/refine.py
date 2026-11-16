"""Verfijning op volle resolutie: trimap + ViTMatte in tegels, guided filter, randkleurcorrectie."""
import numpy as np
from scipy.ndimage import binary_dilation, binary_erosion, uniform_filter

TILE, OVERLAP = 1024, 128


def trimap(alpha, band):
    """0 = achtergrond, 0.5 = onzeker, 1 = voorgrond. band = halve breedte onzekere zone in px."""
    fg = binary_erosion(alpha > 0.95, iterations=band)
    unknown = binary_dilation(alpha > 0.05, iterations=band) & ~fg
    return np.where(fg, 1.0, np.where(unknown, 0.5, 0.0)).astype(np.float32)


def _starts(n):
    if n <= TILE: return [0]
    k = int(np.ceil((n - OVERLAP) / (TILE - OVERLAP)))
    return [round(i * (n - TILE) / (k - 1)) for i in range(k)]


def _ramp(n):
    i = np.arange(n)
    return np.minimum(np.minimum(i + 1, n - i), OVERLAP) / OVERLAP


def vitmatte(sess, rgb, tri):
    """rgb: float32 HxWx3 in 0..1, tri: HxW. Draait alleen op tegels (max 1024 px) met onzekere
    pixels, op de oorspronkelijke resolutie; tegels worden opgevuld tot een veelvoud van 32."""
    h, w = tri.shape
    acc, wsum = np.zeros((h, w), np.float32), np.zeros((h, w), np.float32)
    for y in _starts(h):
        for x in _starts(w):
            t = tri[y:y + TILE, x:x + TILE]
            if not (t == 0.5).any(): continue
            th, tw = t.shape
            inp = np.zeros((1, 4, -(-th // 32) * 32, -(-tw // 32) * 32), np.float32)
            inp[0, :3, :th, :tw] = ((rgb[y:y + th, x:x + tw] - 0.5) / 0.5).transpose(2, 0, 1)
            inp[0, 3, :th, :tw] = t
            a = sess.run(None, {'pixel_values': inp})[0][0, 0, :th, :tw]
            f = np.minimum.outer(_ramp(th), _ramp(tw)).astype(np.float32)
            acc[y:y + th, x:x + tw] += a * f
            wsum[y:y + th, x:x + tw] += f
    out = np.where(tri == 1, 1.0, 0.0).astype(np.float32)
    u = (tri == 0.5) & (wsum > 0)
    out[u] = acc[u] / wsum[u]
    return out


def tile_refine(predict, img, alpha, band):
    """Segmentatiemodel opnieuw op tegels (max 1024 px) op volle resolutie, alleen waar de rand ligt;
    alleen de randzone (trimap 'onzeker') wordt vervangen. predict: PIL-crop → alpha van die crop."""
    tri = trimap(alpha, band)
    h, w = alpha.shape
    acc, wsum = np.zeros((h, w), np.float32), np.zeros((h, w), np.float32)
    for y in _starts(h):
        for x in _starts(w):
            t = tri[y:y + TILE, x:x + TILE]
            if not (t == 0.5).any(): continue
            th, tw = t.shape
            f = np.minimum.outer(_ramp(th), _ramp(tw)).astype(np.float32)
            acc[y:y + th, x:x + tw] += predict(img.crop((x, y, x + tw, y + th))) * f
            wsum[y:y + th, x:x + tw] += f
    out = alpha.copy()
    u = (tri == 0.5) & (wsum > 0)
    out[u] = acc[u] / wsum[u]
    return out


def guided_filter(rgb, p, r, eps=1e-4):
    """Kleur-guided filter (He et al.): randen van p laten aansluiten op de foto."""
    box = lambda x: uniform_filter(x, size=2 * r + 1, mode='reflect')
    mI = np.stack([box(rgb[..., c]) for c in range(3)], -1)
    mp = box(p)
    cov_Ip = np.stack([box(rgb[..., c] * p) for c in range(3)], -1) - mI * mp[..., None]
    var = np.empty(rgb.shape[:2] + (3, 3), np.float32)
    for i in range(3):
        for j in range(i, 3):
            var[..., i, j] = var[..., j, i] = box(rgb[..., i] * rgb[..., j]) - mI[..., i] * mI[..., j]
    var += eps * np.eye(3, dtype=np.float32)
    a = np.linalg.solve(var, cov_Ip[..., None])[..., 0]
    b = mp - (a * mI).sum(-1)
    q = (np.stack([box(a[..., c]) for c in range(3)], -1) * rgb).sum(-1) + box(b)
    return q.clip(0, 1).astype(np.float32)


def foreground(rgb, alpha, r=(90, 6)):
    """Randkleurcorrectie ('blur fusion', Forte & Pitié 2021): schat voorgrondkleur zonder
    achtergrondgloed. rgb, alpha float32 0..1. Geeft RGB terug."""
    a = alpha[..., None]
    F, B = rgb.copy(), rgb.copy()
    for k in r:
        box = lambda x: np.stack([uniform_filter(x[..., c], size=k, mode='reflect') for c in range(x.shape[-1])], -1)
        blur_a = box(a)
        blur_F = box(F * a) / (blur_a + 1e-5)
        blur_B = box(B * (1 - a)) / (box(1 - a) + 1e-5)
        F = (blur_F + a * (rgb - a * blur_F - (1 - a) * blur_B)).clip(0, 1)
        B = blur_B
    return F.astype(np.float32)


if __name__ == '__main__':
    # zelftests: trimap-zones, tegelverdeling dekt alles, guided filter houdt vlakke maskers vlak
    al = np.zeros((50, 50), np.float32); al[10:40, 10:40] = 1
    t = trimap(al, 3)
    assert t[25, 25] == 1 and t[0, 0] == 0 and t[10, 25] == 0.5
    for n in (500, 1024, 1500, 4000):
        s = _starts(n); assert s[0] == 0 and s[-1] + min(TILE, n) == n and all(b - a <= TILE - OVERLAP for a, b in zip(s, s[1:]))
    img = np.random.default_rng(0).random((40, 40, 3), np.float32)
    assert np.allclose(guided_filter(img, np.ones((40, 40), np.float32), 4), 1, atol=1e-3)
    fgc = foreground(np.full((30, 30, 3), 0.3, np.float32), al[:30, :30])
    assert np.allclose(fgc[al[:30, :30] > 0], 0.3, atol=1e-3)  # waar alpha=0 bestaat geen voorgrondkleur
    from PIL import Image
    big = np.zeros((1500, 1200), np.float32); big[300:1200, 300:900] = 1
    half = tile_refine(lambda im: np.full((im.height, im.width), 0.5, np.float32), Image.new('RGB', (1200, 1500)), big, 5)
    tb = trimap(big, 5)
    assert np.allclose(half[tb == 0.5], 0.5) and (half[tb == 1] == 1).all() and (half[tb == 0] == 0).all()
    print('refine zelftest ok')
