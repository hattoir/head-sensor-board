"""配置図 PNG を描く（gen_pcb.py が呼ぶ。KiCad 同梱の Python の PIL を使う）。

基板の外形・部品（ランド・コートヤード）・未配線の接続（ラットネスト）・縁の使い方・寸法を 1 枚に描く。配線はまだ無い。
"""
import math
import pathlib

from PIL import Image, ImageDraw, ImageFont

S = 44.0                   # px / mm
MX, MY = 330, 150          # 基板の左上の余白 [px]
FONT_PATHS = ["C:/Windows/Fonts/meiryo.ttc", "C:/Windows/Fonts/msgothic.ttc", "C:/Windows/Fonts/YuGothR.ttc"]

BG = (246, 246, 242)
BOARD = (22, 92, 58)
EDGE = (250, 225, 90)
PAD = (224, 182, 70)
HOLE = (20, 20, 20)
COURT = (255, 255, 255)


def font(size):
    for p in FONT_PATHS:
        if pathlib.Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()


def net_color(name):
    n = name.upper()
    if n in ("SDA", "SCL"):
        return (90, 170, 255)
    if n.startswith("XSHUT"):
        return (120, 230, 120)
    if n.startswith(("LED_PWM", "GATE")):
        return (255, 160, 60)
    if n.startswith(("LEDA", "LEDK", "SENSE")):
        return (255, 110, 110)
    if n in ("+3V3", "+5V") or n.startswith("NET-("):
        return (255, 70, 70)
    if "INT" in n or "GPIO" in n:
        return (200, 140, 255)
    return (200, 200, 200)


def mst(points):
    """点集合の最小全域木（Prim）。ラットネストの線。"""
    if len(points) < 2:
        return []
    used, edges = [0], []
    rest = list(range(1, len(points)))
    while rest:
        best = None
        for i in used:
            for j in rest:
                d = math.dist(points[i], points[j])
                if best is None or d < best[0]:
                    best = (d, i, j)
        _, i, j = best
        edges.append((points[i], points[j]))
        used.append(j)
        rest.remove(j)
    return edges


def render(geo, out_path):
    W, H, CR = geo["W"], geo["H"], geo["CR"]
    cw, ch = int(W * S + 2 * MX + 120), int(H * S + 2 * MY + 330)
    img = Image.new("RGB", (cw, ch), BG)
    d = ImageDraw.Draw(img, "RGBA")

    def X(x):
        return MX + x * S

    def Y(y):
        return MY + y * S

    f_s, f_m, f_l, f_xl = font(15), font(19), font(25), font(34)

    # --- 基板（角 R1 の長方形）
    def rrect(x0, y0, x1, y1, r, fill=None, outline=None, width=1):
        pts = []
        for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
            for k in range(0, 91, 10):
                a = math.radians(a0 + k)
                pts.append((X(cx + r * math.cos(a)), Y(cy + r * math.sin(a))))
        d.polygon(pts, fill=fill, outline=outline)
        if outline:
            d.line(pts + [pts[0]], fill=outline, width=width)

    rrect(0, 0, W, H, CR, fill=BOARD, outline=EDGE, width=3)

    # --- XIAO モジュールの外形（ソケットの上に載る。ピンの列は下のコートヤード）
    for fp in geo["fps"]:
        if fp["ref"] == "U1":
            cx, cy = fp["c"]
            rot = int(round(fp["rot"])) % 360
            mw, mh = (21.0, 17.8) if rot in (90, 270) else (17.8, 21.0)
            x0, y0, x1, y1 = cx - mw / 2, cy - mh / 2, cx + mw / 2, cy + mh / 2
            d.rectangle((X(x0), Y(y0), X(x1), Y(y1)), fill=(80, 130, 200, 55), outline=(150, 200, 255, 230), width=2)
            d.text((X(cx + 4.6), Y(cy - 1.7)), "XIAO ESP32S3 Sense\n(ソケットに載せる。下の空間に\n小さい部品を置く)", font=f_m, fill=(235, 245, 255),
                   anchor="mm", align="center")

    # --- コートヤード
    for fp in geo["fps"]:
        for poly in fp["court"]:
            if len(poly) >= 3:
                d.polygon([(X(a), Y(b)) for a, b in poly], outline=(255, 255, 255, 120), fill=(255, 255, 255, 18))

    # --- ラットネスト（GND は省く。未配線の接続を示す）
    for name, pads in geo["nets"].items():
        if name == "GND" or len(pads) < 2:
            continue
        col = net_color(name)
        for a, b in mst([p["c"] for p in pads]):
            d.line([(X(a[0]), Y(a[1])), (X(b[0]), Y(b[1]))], fill=col + (170,), width=2)

    # --- ランド
    for fp in geo["fps"]:
        for pd in fp["pads"]:
            cx, cy = pd["c"]
            w, h = pd["w"], pd["h"]
            if pd["shape"] == "round" or (pd["drill"] and abs(w - h) < 0.01):
                d.ellipse((X(cx - w / 2), Y(cy - h / 2), X(cx + w / 2), Y(cy + h / 2)), fill=PAD)
            else:
                d.rectangle((X(cx - w / 2), Y(cy - h / 2), X(cx + w / 2), Y(cy + h / 2)), fill=PAD)
            if pd["drill"]:
                r = pd["drill"] / 2
                d.ellipse((X(cx - r), Y(cy - r), X(cx + r), Y(cy + r)), fill=HOLE)

    # --- 部品名
    off = {"U1": (0, -3.2), "H1": (0, 1.6), "H2": (0, 1.6)}
    for fp in geo["fps"]:
        cx, cy = fp["c"]
        dx, dy = off.get(fp["ref"], (0, 0))
        if fp["ref"] == "U1":
            continue
        txt = fp["ref"] + ("*" if fp["dnp"] else "")
        bb = f_s.getbbox(txt)
        tx, ty = X(cx + dx), Y(cy + dy) - 13
        d.rectangle((tx - (bb[2] - bb[0]) / 2 - 2, ty - 9, tx + (bb[2] - bb[0]) / 2 + 2, ty + 9), fill=(0, 0, 0, 120))
        d.text((tx, ty), txt, font=f_s, fill=(255, 255, 255), anchor="mm")

    # --- 刻印
    for s in geo["silk"]:
        if s["rot"] in (90, 270):
            continue
        d.text((X(s["c"][0]), Y(s["c"][1])), s["text"], font=f_s, fill=(240, 240, 240), anchor="mm")
    d.text((X(1.7), Y(H / 2)), "USB-C", font=f_s, fill=(240, 240, 240), anchor="mm")

    # --- 縁の使い方（注記）
    def arrow(p0, p1, col=(40, 40, 40), w=3):
        d.line([p0, p1], fill=col, width=w)
        a = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
        for s in (-0.45, 0.45):
            d.line([p1, (p1[0] - 16 * math.cos(a + s), p1[1] - 16 * math.sin(a + s))], fill=col, width=w)

    ink = (30, 30, 30)
    # USB-C
    arrow((X(0) - 6, Y(H / 2)), (X(0) - 110, Y(H / 2)), (180, 60, 60), 5)
    d.text((X(0) - 118, Y(H / 2) - 40), "USB-C", font=f_l, fill=(180, 60, 60), anchor="rm")
    d.text((X(0) - 118, Y(H / 2) + 4), "ケーブルは左へ", font=f_m, fill=(180, 60, 60), anchor="rm")
    # LED の縁
    arrow((X(W) + 6, Y(H / 2)), (X(W) + 110, Y(H / 2)), (200, 120, 0), 5)
    d.text((X(W) + 18, Y(H / 2) - 60), "LED の縁", font=f_l, fill=(200, 120, 0), anchor="lm")
    d.text((X(W) + 18, Y(H / 2) - 30), "D1/D2・J3/J4", font=f_m, fill=(200, 120, 0), anchor="lm")
    d.text((X(W) + 18, Y(H / 2) + 30), "床に近い側へ", font=f_m, fill=(200, 120, 0), anchor="lm")
    # ToF
    arrow((X(29), Y(0) - 8), (X(29), Y(0) - 70), (30, 120, 60), 5)
    d.text((X(29) + 14, Y(0) - 64), "ToF R (J2) のジャンパー線は上の縁から", font=f_m, fill=(30, 120, 60), anchor="lm")
    arrow((X(29), Y(H) + 8), (X(29), Y(H) + 70), (30, 120, 60), 5)
    d.text((X(29) + 14, Y(H) + 66), "ToF L (J1) のジャンパー線は下の縁から", font=f_m, fill=(30, 120, 60), anchor="lm")

    # --- 寸法
    def dim_h(x0, x1, y, text):
        d.line([(X(x0), Y(y)), (X(x1), Y(y))], fill=ink, width=2)
        for x in (x0, x1):
            d.line([(X(x), Y(y) - 10), (X(x), Y(y) + 10)], fill=ink, width=2)
        d.text(((X(x0) + X(x1)) / 2, Y(y) - 16), text, font=f_m, fill=ink, anchor="mb")

    def dim_v(y0, y1, x, text):
        d.line([(X(x), Y(y0)), (X(x), Y(y1))], fill=ink, width=2)
        for y in (y0, y1):
            d.line([(X(x) - 10, Y(y)), (X(x) + 10, Y(y))], fill=ink, width=2)
        d.text((X(x) - 16, Y(y0) + 40), text, font=f_m, fill=ink, anchor="rm")        # 上端に書く（USB-C の注記と重ならないように）

    dim_h(0, W, -2.4, f"{W:g} mm（変数 BOARD_W）")
    dim_v(0, H, -1.2, f"{H:g} mm\n(BOARD_H)")

    # --- 凡例
    ly = Y(H) + 150
    d.text((MX, ly), "head-sensor-board Rev A — 部品配置案（上面から見た図。配線なし。配線後の図は render_routed.py）", font=f_xl, fill=ink)
    lines = [
        f"基板 {W:g} × {H:g} mm、角 R{CR:g}、M2 穴 ×2（右の 2 つの角）。下半分 = L チャンネル（XIAO の D0〜D6 の列に近い側）、上半分 = R チャンネル。",
        "細い線 = 未配線の接続（ラットネスト。GND は省略）。青 = I2C、緑 = XSHUT、橙 = LED の PWM・ゲート、赤 = 電源・LED の電流、紫 = ToF の GPIO1。* = 未実装（DNP）。",
        "XIAO は USB-C を左の縁に向けてソケットに載せる。ソケットの内側（薄い青の範囲）には、高さ 0.9 mm 以下の 0603 / 2010 の部品だけを置く。",
        "LED の高さは 0.52 mm。M2 穴は LED の縁側の 2 つの角。",
    ]
    for i, t in enumerate(lines):
        d.text((MX, ly + 52 + i * 30), t, font=f_m, fill=ink)
    img.save(out_path)
    print("PNG:", out_path, img.size)
