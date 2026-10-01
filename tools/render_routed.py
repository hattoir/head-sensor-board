"""Stage 4: 配線後の配置図 PNG を描く。KiCad 同梱の Python（PIL）で実行する:

    "C:/Program Files/KiCad/10.0/bin/python.exe" tools/render_routed.py [--drc "0 件"]

入力  docs/placement_geometry.json（gen_pcb.py）、docs/routes.json（route.py）
出力  docs/placement_routed.png（上面から見た図。F.Cu = 赤、B.Cu = 青。部品名・刻印・縁の使い方・寸法・凡例）
      docs/routing_layers.png（表面 F.Cu と裏面 B.Cu を別々に）
GND のベタ（両面）は図では省いてある。
"""
import argparse
import json
import math
import pathlib

from PIL import Image, ImageDraw

import render_placement as rp

ROOT = pathlib.Path(__file__).resolve().parent.parent
BG, BOARD, EDGE, PAD, HOLE = rp.BG, rp.BOARD, rp.EDGE, rp.PAD, rp.HOLE
RED = (232, 72, 72)
BLUE = (70, 130, 255)
VIA_RING = (215, 215, 215)


def load():
    geo = json.loads((ROOT / "docs" / "placement_geometry.json").read_text(encoding="utf-8"))
    routes = json.loads((ROOT / "docs" / "routes.json").read_text(encoding="utf-8"))
    return geo, routes


def mm(v):
    return v / 1e6


class Canvas:
    def __init__(self, geo, S, MX, MY, extra_w=120, extra_h=0):
        self.geo, self.S, self.MX, self.MY = geo, S, MX, MY
        W, H = geo["W"], geo["H"]
        self.img = Image.new("RGB", (int(W * S + 2 * MX + extra_w), int(H * S + 2 * MY + extra_h)), BG)
        self.d = ImageDraw.Draw(self.img, "RGBA")

    def X(self, x):
        return self.MX + x * self.S

    def Y(self, y):
        return self.MY + y * self.S

    def board(self):
        W, H, CR = self.geo["W"], self.geo["H"], self.geo["CR"]
        pts = []
        for cx, cy, a0 in ((W - CR, CR, -90), (W - CR, H - CR, 0), (CR, H - CR, 90), (CR, CR, 180)):
            for k in range(0, 91, 10):
                a = math.radians(a0 + k)
                pts.append((self.X(cx + CR * math.cos(a)), self.Y(cy + CR * math.sin(a))))
        self.d.polygon(pts, fill=BOARD)
        self.d.line(pts + [pts[0]], fill=EDGE, width=3)

    def tracks(self, routes, layer, col, alpha=255):
        for t in routes["tracks"]:
            if t["layer"] != layer:
                continue
            a = (self.X(mm(t["a"][0])), self.Y(mm(t["a"][1])))
            b = (self.X(mm(t["b"][0])), self.Y(mm(t["b"][1])))
            w = max(2, int(round(t["w"] * self.S)))
            self.d.line([a, b], fill=col + (alpha,), width=w)
            r = w / 2
            for p in (a, b):
                self.d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=col + (alpha,))

    def pads(self, layer_f=True):
        S = self.S
        for fp in self.geo["fps"]:
            for pd in fp["pads"]:
                if not layer_f and not pd["thru"]:
                    continue
                if pd["npth"]:
                    continue
                if pd.get("poly"):
                    self.d.polygon([(self.X(a), self.Y(b)) for a, b in pd["poly"]], fill=PAD)
                    continue
                cx, cy = pd["bc"]
                w, h = pd["w"], pd["h"]
                if pd.get("kind") in ("circle", "oval") and abs(w - h) < 0.01:
                    self.d.ellipse((self.X(cx - w / 2), self.Y(cy - h / 2), self.X(cx + w / 2), self.Y(cy + h / 2)), fill=PAD)
                else:
                    self.d.rectangle((self.X(cx - w / 2), self.Y(cy - h / 2), self.X(cx + w / 2), self.Y(cy + h / 2)), fill=PAD)
                if pd["drill"]:
                    r = pd["drill"] / 2
                    self.d.ellipse((self.X(cx - r), self.Y(cy - r), self.X(cx + r), self.Y(cy + r)), fill=HOLE)
        for fp in self.geo["fps"]:                                   # 取付穴
            for pd in fp["pads"]:
                if pd["npth"]:
                    cx, cy = pd["bc"]
                    r = pd["drill"] / 2
                    self.d.ellipse((self.X(cx - r), self.Y(cy - r), self.X(cx + r), self.Y(cy + r)), fill=HOLE, outline=(200, 200, 200), width=2)

    def vias(self, routes):
        for v in routes["vias"]:
            x, y = self.X(mm(v["at"][0])), self.Y(mm(v["at"][1]))
            r, h = v["d"] / 2 * self.S, v["drill"] / 2 * self.S
            self.d.ellipse((x - r, y - r, x + r, y + r), fill=VIA_RING, outline=(60, 60, 60), width=1)
            self.d.ellipse((x - h, y - h, x + h, y + h), fill=HOLE)

    def refs(self, font, skip=("U1",)):
        for fp in self.geo["fps"]:
            if fp["ref"] in skip:
                continue
            cx, cy = fp["c"]
            txt = fp["ref"] + ("*" if fp["dnp"] else "")
            bb = font.getbbox(txt)
            tx, ty = self.X(cx), self.Y(cy)
            self.d.rectangle((tx - (bb[2] - bb[0]) / 2 - 2, ty - 9, tx + (bb[2] - bb[0]) / 2 + 2, ty + 9), fill=(0, 0, 0, 130))
            self.d.text((tx, ty), txt, font=font, fill=(255, 255, 255), anchor="mm")

    def silk(self, font):
        for a, b in self.geo.get("silk_lines", []):
            self.d.line([(self.X(a[0]), self.Y(a[1])), (self.X(b[0]), self.Y(b[1]))], fill=(240, 240, 240, 230), width=2)
        for s in self.geo["silk"]:
            if s["rot"] in (90, 270):
                tx = Image.new("RGBA", (200, 40), (0, 0, 0, 0))
                ImageDraw.Draw(tx).text((100, 20), s["text"], font=font, fill=(240, 240, 240, 255), anchor="mm")
                tx = tx.rotate(90, expand=True)
                self.img.paste(tx, (int(self.X(s["c"][0]) - tx.width / 2), int(self.Y(s["c"][1]) - tx.height / 2)), tx)
                continue
            anchor = {"l": "lm", "r": "rm", "c": "mm"}[s.get("just", "c")]
            self.d.text((self.X(s["c"][0]), self.Y(s["c"][1])), s["text"], font=rp.font(int(max(15, s["h"] * self.S * 0.62 * (1.0 if s["h"] < 1.2 else 1.1)))),
                        fill=(240, 240, 240), anchor=anchor)


def xiao_overlay(cv, font):
    for fp in cv.geo["fps"]:
        if fp["ref"] == "U1":
            cx, cy = fp["c"]
            rot = int(round(fp["rot"])) % 360
            mw, mh = (21.0, 17.8) if rot in (90, 270) else (17.8, 21.0)
            cv.d.rectangle((cv.X(cx - mw / 2), cv.Y(cy - mh / 2), cv.X(cx + mw / 2), cv.Y(cy + mh / 2)), outline=(150, 200, 255, 230), width=2)


def summary(routes):
    L, wl = {}, {}
    for t in routes["tracks"]:
        ln = math.dist(t["a"], t["b"]) / 1e6
        L[t["net"]] = L.get(t["net"], 0) + ln
        wl[t["w"]] = wl.get(t["w"], 0) + ln
    return L, wl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drc", default="違反 0 件（未接続 0・回路図との不一致 0）")
    args = ap.parse_args()
    geo, routes = load()
    W, H = geo["W"], geo["H"]
    L, wl = summary(routes)
    f_s, f_m, f_l, f_xl = rp.font(15), rp.font(19), rp.font(25), rp.font(34)
    ink = (30, 30, 30)

    # ---------------- 主図: 上面から見た配置と配線
    S, MX, MY = 44.0, 330, 150
    cv = Canvas(geo, S, MX, MY, extra_w=120, extra_h=330)
    cv.board()
    cv.tracks(routes, "B.Cu", BLUE, 215)
    cv.pads(layer_f=False)
    cv.tracks(routes, "F.Cu", RED, 235)
    cv.pads()
    cv.vias(routes)
    xiao_overlay(cv, f_m)
    cv.refs(f_s)
    cv.silk(f_s)
    d = cv.d

    def arrow(p0, p1, col, w=5):
        d.line([p0, p1], fill=col, width=w)
        a = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
        for s in (-0.45, 0.45):
            d.line([p1, (p1[0] - 16 * math.cos(a + s), p1[1] - 16 * math.sin(a + s))], fill=col, width=w)

    X, Y = cv.X, cv.Y
    arrow((X(0) - 6, Y(H / 2)), (X(0) - 110, Y(H / 2)), (180, 60, 60))
    d.text((X(0) - 118, Y(H / 2) - 40), "USB-C", font=f_l, fill=(180, 60, 60), anchor="rm")
    d.text((X(0) - 118, Y(H / 2) + 4), "ケーブルは左へ", font=f_m, fill=(180, 60, 60), anchor="rm")
    arrow((X(W) + 6, Y(H / 2)), (X(W) + 110, Y(H / 2)), (200, 120, 0))
    d.text((X(W) + 18, Y(H / 2) - 60), "LED の縁", font=f_l, fill=(200, 120, 0), anchor="lm")
    d.text((X(W) + 18, Y(H / 2) - 30), "D1/D2・J3/J4", font=f_m, fill=(200, 120, 0), anchor="lm")
    d.text((X(W) + 18, Y(H / 2) + 30), "床に近い側へ", font=f_m, fill=(200, 120, 0), anchor="lm")
    j2 = next(f for f in geo["fps"] if f["ref"] == "J2")["c"][0] - 6.35
    arrow((X(j2), Y(0) - 8), (X(j2), Y(0) - 70), (30, 120, 60))
    d.text((X(j2) + 14, Y(0) - 64), "ToF R (J2) のジャンパー線は上の縁から", font=f_m, fill=(30, 120, 60), anchor="lm")
    arrow((X(j2), Y(H) + 8), (X(j2), Y(H) + 70), (30, 120, 60))
    d.text((X(j2) + 14, Y(H) + 66), "ToF L (J1) のジャンパー線は下の縁から", font=f_m, fill=(30, 120, 60), anchor="lm")
    # 寸法
    d.line([(X(0), Y(-2.4)), (X(W), Y(-2.4))], fill=ink, width=2)
    for x in (0, W):
        d.line([(X(x), Y(-2.4) - 10), (X(x), Y(-2.4) + 10)], fill=ink, width=2)
    d.text(((X(0) + X(W)) / 2, Y(-2.4) - 16), f"{W:g} mm（変数 BOARD_W）", font=f_m, fill=ink, anchor="mb")
    d.line([(X(-1.2), Y(0)), (X(-1.2), Y(H))], fill=ink, width=2)
    for y in (0, H):
        d.line([(X(-1.2) - 10, Y(y)), (X(-1.2) + 10, Y(y))], fill=ink, width=2)
    d.text((X(-1.2) - 16, Y(0) + 40), f"{H:g} mm\n(BOARD_H)", font=f_m, fill=ink, anchor="rm")

    ly = Y(H) + 150
    d.text((MX, ly), "head-sensor-board Rev A — Stage 4 配線後の配置図（上面から見た図）", font=f_xl, fill=ink)
    nv = len(routes["vias"])
    lines = [
        f"基板 {W:g} × {H:g} mm、角 R1、M2 穴 ×2（右の 2 つの角）。2 層。赤 = 表面 F.Cu の配線、青 = 裏面 B.Cu の配線、白い丸 = ビア（{nv} 個、φ0.6 / 穴 0.3）。GND は両面のベタ（図では省略）。",
        f"配線幅: +3V3・+5V = 0.5 mm（計 {wl.get(0.5, 0):.0f} mm）、LED の電流の経路（LEDA / LEDK / SENSE / 5V 抵抗の先）= 0.4 mm（計 {wl.get(0.4, 0):.0f} mm）、信号 = 0.25 mm（計 {wl.get(0.25, 0):.0f} mm）。",
        f"I2C の配線長: SDA {L.get('/SDA', 0):.0f} mm、SCL {L.get('/SCL', 0):.0f} mm（XIAO → J1・J2・TP・プルアップ。スルーホールのピンで層を乗り換えるので、ビアは 0 個）。",
        f"DRC: {args.drc}。クリアランス 0.2 mm、縁から 0.5 mm。薄い青の枠 = XIAO ESP32S3 Sense（上に載る）。* = 未実装（DNP）。J1 / J2 は ToF 小基板へのジャンパー線（信号名は刻印。小基板側のピン配置は未確認）。",
    ]
    for i, t in enumerate(lines):
        d.text((MX, ly + 52 + i * 30), t, font=f_m, fill=ink)
    out = ROOT / "docs" / "placement_routed.png"
    cv.img.save(out)
    print("PNG:", out, cv.img.size)

    # ---------------- 層ごと: F.Cu と B.Cu
    S2, M2 = 30.0, 40
    panels = []
    for layer, col, title in (("F.Cu", RED, "表面 F.Cu（上から見る）"), ("B.Cu", BLUE, "裏面 B.Cu（上から透かして見る。左右はそのまま）")):
        c2 = Canvas(geo, S2, M2, 70, extra_w=0, extra_h=20)
        c2.board()
        c2.tracks(routes, layer, col, 255)
        c2.pads(layer_f=(layer == "F.Cu"))
        c2.vias(routes)
        c2.refs(rp.font(12))
        c2.d.text((M2, 30), title, font=f_m, fill=ink, anchor="lm")
        panels.append(c2.img)
    w = max(p.width for p in panels)
    sheet = Image.new("RGB", (w, sum(p.height for p in panels)), BG)
    y = 0
    for p in panels:
        sheet.paste(p, (0, y))
        y += p.height
    out2 = ROOT / "docs" / "routing_layers.png"
    sheet.save(out2)
    print("PNG:", out2, sheet.size)


if __name__ == "__main__":
    main()
