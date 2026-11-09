"""Composite Korean print text onto the white paper revealed in the tear video,
then add an animated CTA button. Outputs 9:16 (1080x1920) and 4:5 (1080x1350)."""
import json, subprocess, sys, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

SRC, OUTDIR, CFG = sys.argv[1], sys.argv[2], json.load(open(sys.argv[3]))
W, H = 1080, 1920
FD = "/tmp/claude-0/-home-user-assam/530502a6-f27b-59d5-a737-eda58e101776/scratchpad/fonts"
F_MJ_B = f"{FD}/kf/package/src/NanumMyeongjoBold.ttf"
F_MJ_XB = f"{FD}/kf/package/src/NanumMyeongjoExtraBold.ttf"
F_PRE = f"{FD}/package/dist/public/static/Pretendard-Bold.otf"
F_PRE_SB = f"{FD}/package/dist/public/static/Pretendard-SemiBold.otf"
F_CG_I = f"{FD}/package/files/cormorant-garamond-latin-600-italic.woff2"
INK = tuple(CFG.get("ink", [38, 33, 30]))

# ---------- print layer (ink on paper), grayscale alpha ----------
SS = 2  # supersample
ink = Image.new("L", (W * SS, H * SS), 0)
d = ImageDraw.Draw(ink)

def ctext(y, txt, path, size, tracking=0):
    f = ImageFont.truetype(path, size * SS)
    if tracking:
        widths = [d.textlength(c, font=f) for c in txt]
        total = sum(widths) + tracking * SS * (len(txt) - 1)
        x = CFG.get("text_cx", W / 2) * SS - total / 2
        for c, w in zip(txt, widths):
            d.text((x, y * SS), c, font=f, fill=255, anchor="ls")
            x += w + tracking * SS
    else:
        d.text((CFG.get("text_cx", W / 2) * SS, y * SS), txt, font=f, fill=255, anchor="ms")

L = CFG["layout"]
PRE = lambda w: f"{FD}/package/dist/public/static/Pretendard-{w}.otf"
for ln in CFG["lines"]:
    ctext(ln["y"], ln["text"], PRE(ln["weight"]), ln["size"], tracking=ln.get("track", 0))
ink = ink.resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.6))
ink_a = np.asarray(ink, np.float32) / 255.0 * CFG.get("ink_opacity", 0.92)
ink_col = np.array(INK, np.float32) / 255.0

# ---------- CTA button (RGBA) ----------
B = CFG["button"]
bw, bh = B["w"], B["h"]
pad = 60
btn = Image.new("RGBA", ((bw + 2 * pad) * SS, (bh + 2 * pad) * SS), (0, 0, 0, 0))
bd = ImageDraw.Draw(btn)
# soft shadow
sh = Image.new("RGBA", btn.size, (0, 0, 0, 0))
ImageDraw.Draw(sh).rounded_rectangle(
    [pad * SS, (pad + 14) * SS, (pad + bw) * SS, (pad + bh + 14) * SS],
    radius=bh * SS // 2, fill=tuple(B.get("shadow", [40, 25, 10, 110])))
sh = sh.filter(ImageFilter.GaussianBlur(18 * SS))
btn.alpha_composite(sh)
bd.rounded_rectangle([pad * SS, pad * SS, (pad + bw) * SS, (pad + bh) * SS],
                     radius=bh * SS // 2, fill=tuple(B["bg"]) + (255,))
bf = ImageFont.truetype(F_PRE, B["size"] * SS)
label = "무료 사전 예약하기"
arrow = "  →"
bt = B.get("track", 0) * SS
txt = label + arrow
ws = [bd.textlength(c, font=bf) for c in txt]
x = (pad + bw / 2) * SS - (sum(ws) + bt * (len(txt) - 1)) / 2
for c, w_ in zip(txt, ws):
    bd.text((x, (pad + bh / 2) * SS), c, font=bf, fill=tuple(B["fg"]) + (255,), anchor="lm")
    x += w_ + bt
btn = btn.resize((bw + 2 * pad, bh + 2 * pad), Image.LANCZOS)
btn_np = np.asarray(btn, np.float32) / 255.0
# button-shaped mask for the shine sweep
bmask = Image.new("L", btn.size, 0)
ImageDraw.Draw(bmask).rounded_rectangle([pad, pad, pad + bw, pad + bh], radius=bh // 2, fill=255)
bmask = np.asarray(bmask, np.float32) / 255.0

def ease_out_back(t):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2

def button_frame(t):
    """Return (rgba np array, scale) for time t or None."""
    t0 = B["t_in"]
    if t < t0:
        return None
    k = min(1.0, (t - t0) / 0.45)
    s = 0.6 + 0.4 * ease_out_back(k)
    alpha = min(1.0, (t - t0) / 0.25)
    if k >= 1:  # gentle pulse
        s *= 1 + 0.035 * math.sin((t - t0 - 0.45) * 2 * math.pi / 1.1)
    img = btn_np.copy()
    # shine sweep every 1.6 s after pop
    ts = (t - t0 - 0.5) % 1.6
    if t - t0 > 0.5 and ts < 0.6:
        hh, ww = img.shape[:2]
        xs = np.arange(ww)[None, :] - (np.arange(hh)[:, None] * 0.5)
        cx = -100 + (ww + 200) * (ts / 0.6)
        band = np.clip(1 - np.abs(xs - cx) / 40, 0, 1) * 0.35 * bmask
        img[..., :3] = img[..., :3] + (1 - img[..., :3]) * band[..., None]
    img[..., 3] *= alpha
    return img, s

def paste_rgba(frame, rgba, cx, cy, scale):
    h, w = rgba.shape[:2]
    if abs(scale - 1) > 1e-3:
        im = Image.fromarray((rgba * 255).astype(np.uint8), "RGBA")
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.BICUBIC)
        rgba = np.asarray(im, np.float32) / 255.0
        h, w = rgba.shape[:2]
    x0, y0 = int(cx - w / 2), int(cy - h / 2)
    fx0, fy0 = max(0, x0), max(0, y0)
    fx1, fy1 = min(W, x0 + w), min(H, y0 + h)
    sub = rgba[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0]
    a = sub[..., 3:4]
    frame[fy0:fy1, fx0:fx1] = frame[fy0:fy1, fx0:fx1] * (1 - a) + sub[..., :3] * a

# ---------- paper mask ----------
M = CFG["mask"]
def paper_mask(fr):
    r, g, b = fr[..., 0], fr[..., 1], fr[..., 2]
    mx = fr.max(-1); mn = fr.min(-1)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    sat = (mx - mn) / (mx + 1e-4)
    m = np.clip((lum - M["lum_lo"]) / (M["lum_hi"] - M["lum_lo"]), 0, 1) * \
        np.clip((M["sat_hi"] - sat) / (M["sat_hi"] - M["sat_lo"]), 0, 1)
    im = Image.fromarray((m * 255).astype(np.uint8))
    im = im.filter(ImageFilter.MinFilter(M.get("erode", 5))).filter(ImageFilter.GaussianBlur(M.get("blur", 2.5)))
    return np.asarray(im, np.float32) / 255.0

# ---------- process ----------
fps = CFG.get("fps", 30)
SS_T = str(CFG.get("ss", 0)); PRE = CFG.get("pre_vf", "")
dec = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", SS_T, "-i", SRC, "-vf",
                        f"{PRE}fps={fps},scale={W}:{H}:flags=lanczos,setsar=1",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                        "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-ss", SS_T, "-i", SRC,
                        "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-preset", "slow",
                        "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                        "-shortest", "-movflags", "+faststart", f"{OUTDIR}/master_9x16.mp4"],
                       stdin=subprocess.PIPE)
n = 0
y0, y1 = L["ink_y0"], L["ink_y1"]
while True:
    buf = dec.stdout.read(W * H * 3)
    if len(buf) < W * H * 3:
        break
    fr = np.frombuffer(buf, np.uint8).reshape(H, W, 3).astype(np.float32) / 255.0
    t = n / fps
    band = fr[y0:y1]
    a = (ink_a[y0:y1] * paper_mask(band))[..., None]
    # multiply-blend ink so paper shading shows through the print
    fr[y0:y1] = band * (1 - a) + band * ink_col * a
    bf_ = button_frame(t)
    if bf_ is not None:
        paste_rgba(fr, bf_[0], W / 2, B["cy"], bf_[1])
    enc.stdin.write((np.clip(fr, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes())
    if n in CFG.get("snap", []):
        Image.fromarray((np.clip(fr, 0, 1) * 255).astype(np.uint8)).save(f"{OUTDIR}/snap_{n:04d}.jpg", quality=88)
    n += 1
enc.stdin.close(); enc.wait(); dec.wait()
print("frames", n)
