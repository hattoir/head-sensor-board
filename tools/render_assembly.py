"""組み立て図（どこにどの部品を置くか）と、部品の置き場の表を作る。KiCad 同梱の Python（PIL）で実行する:

    "C:/Program Files/KiCad/10.0/bin/python.exe" tools/render_assembly.py

入力  docs/placement_geometry.json（gen_pcb.py が作る。基板の部品の位置・ランド）
出力  docs/assembly_guide.png（上面から見た図。部品名・値・向き・組み立ての順で色分け）
      docs/assembly_guide.md（表: 記号 / 買った部品 / 基板の左上からの位置 / 向き / 順）
部品の値・買った部品の名前は PARTS に書いてある（BOM と購入リストから）。位置は基板の実際のデータから出す。
"""
import json
import math
import pathlib

from PIL import ImageDraw

import render_placement as rp
import render_routed as rr

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 組み立ての順: 1 = 小さいチップ部品（抵抗・コンデンサ）、2 = MOSFET、3 = LED、4 = ピンヘッダ・ソケット（スルーホール）、5 = 半田ジャンパー、6 = XIAO
STEP_COLOR = {1: (70, 130, 255), 2: (170, 90, 230), 3: (255, 210, 40), 4: (200, 200, 200), 5: (60, 220, 220), 6: (120, 200, 255)}
STEP_NAME = {1: "チップ抵抗・コンデンサ", 2: "MOSFET", 3: "LED", 4: "ピンヘッダ・ソケット", 5: "半田ジャンパー", 6: "XIAO（最後）"}

# 記号 → (表示の値, 買った部品, 順, 向きなどのメモ, 実装しない)
PARTS = {}
for ref, val, buy in (("R1", "20Ω", "チップ抵抗 20 Ω 1608"), ("R2", "20Ω", "チップ抵抗 20 Ω 1608"),
                      ("R5", "220Ω", "チップ抵抗 220 Ω 1608"), ("R6", "220Ω", "チップ抵抗 220 Ω 1608"),
                      ("R7", "100k", "チップ抵抗 100 kΩ 1608"), ("R8", "100k", "チップ抵抗 100 kΩ 1608"),
                      ("R9", "1Ω±1%", "チップ抵抗 1 Ω ±1 % 1608"), ("R10", "1Ω±1%", "チップ抵抗 1 Ω ±1 % 1608"),
                      ("R11", "10k", "チップ抵抗 10 kΩ 1608"), ("R12", "10k", "チップ抵抗 10 kΩ 1608")):
    PARTS[ref] = (val, buy, 1, "向きなし", False)
for ref in ("R3", "R4"):
    PARTS[ref] = ("33Ω", "チップ抵抗 33 Ω 2010（0.5 W 以上）", 1, "向きなし。5V の LED 用。使わないなら載せなくてよい", False)
for ref, val in (("R13", "3.3k"), ("R14", "3.3k")):
    PARTS[ref] = (val, "チップ抵抗 3.3 kΩ 1608", 1, "**未実装**（I2C のプルアップ。ToF 小基板に無いと分かったときだけ）", True)
for ref in ("R15", "R16"):
    PARTS[ref] = ("0Ω", "チップ抵抗 0 Ω 1608", 1, "**未実装**（ToF の GPIO1 を使うときだけ）", True)
PARTS["C1"] = ("10µF", "チップコンデンサ 10 µF 2012（0805）", 1, "向きなし", False)
PARTS["C2"] = ("0.1µ", "チップコンデンサ 0.1 µF 1608", 1, "向きなし", False)
PARTS["C3"] = ("0.1µ", "チップコンデンサ 0.1 µF 1608", 1, "向きなし", False)
PARTS["Q1"] = ("MTN2306", "MOSFET MTN2306AN3（SOT-23）", 2, "**ピン 1（ゲート）は左上**。左の 2 つがゲート（上）・ソース（下）、右の 1 つがドレイン", False)
PARTS["Q2"] = ("MTN2306", "MOSFET MTN2306AN3（SOT-23）", 2, "**ピン 1（ゲート）は左上**。左の 2 つがゲート（上）・ソース（下）、右の 1 つがドレイン", False)
PARTS["D1"] = ("LED", "LED NSSW157T", 3, "**カソード（K）は左の大きいパッド**、アノード（A）は右。リフローかホットエア。樹脂を押さない", False)
PARTS["D2"] = ("LED", "LED NSSW157T", 3, "**カソード（K）は左の大きいパッド**、アノード（A）は右。リフローかホットエア。樹脂を押さない", False)
PARTS["J1"] = ("ToF-L", "ピンヘッダ 1×6（オス）", 4, "**四角いパッド = ピン 1 = VIN = 右端**。長いピンを上（ジャンパー線側）、短いピンを基板の穴へ", False)
PARTS["J2"] = ("ToF-R", "ピンヘッダ 1×6（オス）", 4, "**四角いパッド = ピン 1 = VIN = 右端**。長いピンを上、短いピンを基板の穴へ", False)
PARTS["J3"] = ("LED-L外付", "ピンヘッダ 1×2（オス）", 4, "任意（外付け LED 用）。**ピン 1（四角）= +、左**。+ と − を短絡しない", False)
PARTS["J4"] = ("LED-R外付", "ピンヘッダ 1×2（オス）", 4, "任意（外付け LED 用）。**ピン 1（四角）= +、左**", False)
PARTS["SJ1"] = ("SJ", "（部品なし。はんだのパッド）", 5, "**既定は 1-2 が銅でつながっている = 3V3。何もしない**。5V にするときだけ、1-2 の橋を切って 2-3 をはんだでつなぐ", False)
PARTS["SJ2"] = ("SJ", "（部品なし。はんだのパッド）", 5, "同上", False)
PARTS["U1"] = ("XIAO", "XIAO ESP32S3 Sense + ピンソケット 1×7（メス）×2", 6, "**USB-C を左**。先にソケットを基板にはんだ付け（XIAO にヘッダを付けて差したまま付けると位置が合う）。XIAO は最後", False)
for i in range(1, 9):
    PARTS[f"TP{i}"] = ("TP", "（部品なし。測定用の丸いパッド）", 0, "プローブを当てる / 線をはんだ付けする", False)
for h in ("H1", "H2"):
    PARTS[h] = ("M2穴", "（M2 ねじの穴。任意）", 0, "頭への取り付けが決まってから", False)


def label_font(size):
    return rp.font(size)


def main():
    geo = json.loads((ROOT / "docs" / "placement_geometry.json").read_text(encoding="utf-8"))
    W, H = geo["W"], geo["H"]
    S, MX, MY = 62.0, 80, 150
    cv = rr.Canvas(geo, S, MX, MY, extra_w=40, extra_h=520)
    d = cv.d
    X, Y = cv.X, cv.Y
    cv.board()
    cv.pads()
    rr.xiao_overlay(cv, label_font(20))
    f_ref, f_val, f_s, f_m, f_l, f_xl = label_font(21), label_font(16), label_font(15), label_font(20), label_font(26), label_font(36)

    def pad_bbox(fp, margin):
        xs0, ys0, xs1, ys1 = 1e9, 1e9, -1e9, -1e9
        for p in fp["pads"]:
            cx, cy = p["bc"]
            xs0, ys0 = min(xs0, cx - p["w"] / 2), min(ys0, cy - p["h"] / 2)
            xs1, ys1 = max(xs1, cx + p["w"] / 2), max(ys1, cy + p["h"] / 2)
        return xs0 - margin, ys0 - margin, xs1 + margin, ys1 + margin

    for fp in geo["fps"]:
        ref = fp["ref"]
        val, buy, step, note, dnp = PARTS[ref]
        if step == 0:
            continue
        x0, y0, x1, y1 = pad_bbox(fp, 0.25)
        col = (150, 150, 150) if dnp else STEP_COLOR[step]
        d.rectangle((X(x0), Y(y0), X(x1), Y(y1)), outline=col + (255,), fill=col + (60,), width=3)
        if dnp:                                                                     # 未実装は ×
            d.line([(X(x0), Y(y0)), (X(x1), Y(y1))], fill=(255, 80, 80, 230), width=3)
            d.line([(X(x0), Y(y1)), (X(x1), Y(y0))], fill=(255, 80, 80, 230), width=3)
    # 部品名と値（部品の中心に。暗い帯の上に白い字）
    for fp in geo["fps"]:
        ref = fp["ref"]
        val, buy, step, note, dnp = PARTS[ref]
        if step == 0 or ref == "U1":
            continue
        cx, cy = fp["c"]
        if ref in ("J1", "J2", "J3", "J4", "SJ1", "SJ2"):                           # 大きい部品は、ラベルを部品の脇へ
            xs = [p["bc"][0] for p in fp["pads"]]
            ys = [p["bc"][1] for p in fp["pads"]]
            cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        txt1 = ref + ("（未実装）" if dnp else "")
        w1 = f_ref.getbbox(txt1)[2]
        w2 = f_val.getbbox(val)[2]
        bw = max(w1, w2) / 2 + 4
        px, py = X(cx), Y(cy)
        d.rectangle((px - bw, py - 21, px + bw, py + 19), fill=(0, 0, 0, 175))
        d.text((px, py - 9), txt1, font=f_ref, fill=(255, 255, 255), anchor="mm")
        d.text((px, py + 10), val, font=f_val, fill=(255, 230, 120) if not dnp else (200, 200, 200), anchor="mm")
    # 向きの印: LED（K / A）、MOSFET（G / S / D）、ヘッダのピン 1、J3/J4（+）
    for fp in geo["fps"]:
        ref = fp["ref"]
        pads = {p["n"]: p for p in fp["pads"]}
        marks = []
        if ref in ("D1", "D2"):
            marks = [("1", "K"), ("2", "A")]
        elif ref in ("Q1", "Q2"):
            marks = [("1", "G"), ("2", "S"), ("3", "D")]
        elif ref in ("J1", "J2"):
            marks = [("1", "1 VIN")]
        elif ref in ("J3", "J4"):
            marks = [("1", "1 +"), ("2", "2 −")]
        for n, t in marks:
            p = pads[n]
            cx, cy = p["bc"]
            dy = {"D1": 1.35, "D2": 1.35, "Q1": 0, "Q2": 0}.get(ref, 0)
            ox, oy = (0, -1.35) if ref in ("D1", "D2") else ((-0.95, 0) if ref in ("Q1", "Q2") and n in ("1", "2") else ((0.95, 0) if ref in ("Q1", "Q2") else (0, 1.55)))
            if ref in ("J1", "J2"):
                oy = 1.55 if fp["c"][1] < H / 2 else -1.55                 # ヘッダの内側（基板の中心側）
            tx, ty = X(cx + ox), Y(cy + oy)
            w = f_m.getbbox(t)[2] / 2 + 4
            d.rectangle((tx - w, ty - 13, tx + w, ty + 13), fill=(255, 255, 255, 235), outline=(0, 0, 0), width=1)
            d.text((tx, ty), t, font=f_m, fill=(180, 0, 0), anchor="mm")
    # XIAO
    u1 = next(f for f in geo["fps"] if f["ref"] == "U1")
    ucx, ucy = u1["c"]
    d.text((X(ucx + 3.0), Y(ucy + 0.2)), "XIAO ESP32S3 Sense", font=f_l, fill=(220, 240, 255), anchor="mm")
    d.text((X(ucx + 3.0), Y(ucy + 1.7)), "（最後に載せる。USB-C は左）", font=f_m, fill=(220, 240, 255), anchor="mm")
    d.text((X(ucx - 4.2), Y(ucy - 6.9)), "ソケット 1×7（上の列）", font=f_s, fill=(255, 255, 255), anchor="mm")
    d.text((X(ucx - 4.2), Y(ucy + 7.0)), "ソケット 1×7（下の列）", font=f_s, fill=(255, 255, 255), anchor="mm")
    # 矢印と注記
    d.text((MX, MY - 22), "← USB-C（ケーブルは左）", font=f_m, fill=(180, 60, 60), anchor="lm")
    for fp in geo["fps"]:
        if fp["ref"].startswith("TP"):
            d.text((X(fp["c"][0]), Y(fp["c"][1])), fp["ref"], font=f_s, fill=(40, 40, 40), anchor="mm")
    ink = (30, 30, 30)
    d.text((MX, 40), "head-sensor-board Rev A — 組み立て図（上面から見た図。部品は全部、上面に載せる）", font=f_xl, fill=ink)
    d.text((MX, 90), "色 = 組み立ての順。部品名 = 基板の記号、黄色の字 = 値。赤い × = 既定では載せない（未実装）。赤い小さな札 = 向きの印。", font=f_m, fill=ink)
    # 凡例
    ly = Y(H) + 60
    d.text((MX, ly), "組み立ての順（小さい・低い部品から。XIAO は最後）", font=f_l, fill=ink)
    items = [(1, "1  チップ抵抗・コンデンサ（R1〜R12、C1〜C3。R3/R4 は任意）"), (2, "2  MOSFET（Q1・Q2）"), (3, "3  LED（D1・D2。ホットエア、向きに注意）"),
             (4, "4  ピンヘッダ J1・J2（J3・J4 は任意）と、XIAO 用ソケット 1×7 ×2"), (5, "5  半田ジャンパー SJ1・SJ2（既定は何もしない）"), (6, "6  XIAO をソケットに載せる（最後）")]
    for i, (st, t) in enumerate(items):
        yy = ly + 50 + i * 36
        d.rectangle((MX, yy, MX + 34, yy + 24), fill=STEP_COLOR[st] + (255,), outline=(0, 0, 0))
        d.text((MX + 48, yy + 12), t, font=f_m, fill=ink, anchor="lm")
    d.text((MX + 1250, ly + 50), "載せない: R13・R14（3.3 kΩ）、R15・R16（0 Ω）= 赤い ×。TP1〜TP8 は測定用のパッドで部品なし。", font=f_m, fill=ink)
    d.text((MX + 1250, ly + 86), "J1/J2 のピン 1（四角いパッド）は右端 = VIN。ToF 小基板の並びは未確認 → 現物で README の対応表を埋める。", font=f_m, fill=ink)
    d.text((MX + 1250, ly + 122), "LED は 2 個とも「左が K（カソード）」。MOSFET は 2 個とも「ピン 1 が左上」。", font=f_m, fill=ink)
    cv.img.save(ROOT / "docs" / "assembly_guide.png")
    print("PNG:", ROOT / "docs" / "assembly_guide.png", cv.img.size)

    # ---- 表
    lines = ["# 組み立ての置き場の表（`tools/render_assembly.py` が基板のデータから作る。手で直さない）", "",
             "図: [assembly_guide.png](assembly_guide.png)。位置は**基板の左上の角から**（x = 右へ、y = 下へ、mm、部品の中心）。上面から見て USB-C を左にした向き。",
             "**順 1 → 6 で載せる**（小さい・低い部品から。XIAO は最後）。", "",
             "| 順 | 記号 | 値 | 買った部品 | 位置（x, y mm） | どのあたり | 向き・注意 |", "|---|---|---|---|---|---|---|"]

    def area(fp):
        x, y = fp["c"]
        ref = fp["ref"]
        if ref.startswith("TP"):
            return "上の縁の左" if y < H / 2 and x < 12 else ("右のゾーンの中央" if x > 28 and x < 36 and 8 < y < 20 else "上下の縁")
        if ref in ("J1", "J2"):
            return "下の縁（ToF L）" if ref == "J1" else "上の縁（ToF R）"
        if ref in ("J3", "J4"):
            return "下の縁の右寄り" if y > H / 2 else "上の縁の右寄り"
        if ref in ("H1", "H2"):
            return "右下の角" if y > H / 2 else "右上の角"
        if x < 22 and 5.1 < y < H - 5.1:
            return "XIAO の下（ソケットの内側）"
        return ("右のゾーン・下半分（L チャンネル）" if y > H / 2 else "右のゾーン・上半分（R チャンネル）")

    order = sorted(geo["fps"], key=lambda f: (PARTS[f["ref"]][2] if PARTS[f["ref"]][2] else 9, f["ref"][0] != "R", len(f["ref"]), f["ref"]))
    for fp in order:
        ref = fp["ref"]
        val, buy, step, note, dnp = PARTS[ref]
        lines.append(f"| {step if step else '—'} | **{ref}** | {val} | {buy} | ({fp['c'][0]:.1f}, {fp['c'][1]:.1f}) | {area(fp)} | {note} |")
    lines += ["", "## 補足", "",
              "- **R13・R14・R15・R16 は載せない**（図の赤い ×）。TP1〜TP8 は測定用の丸いパッドで、部品は載せない（チェック端子は付かない）。",
              "- **MOSFET は MTN2306AN3**（秋月 g117513）。データシートでピン 1 = ゲート、2 = ソース、3 = ドレインと確認済み（基板と同じ）。BOM の AO3400A の代わりに使える。",
              "- **XIAO の下の部品（R3〜R8、R11〜R16、C1〜C3 の大半）は、ソケットを付ける前に載せる**。ソケットの後ではこてが入らない。",
              "- ソケットの付け方: XIAO に付属のヘッダ（オス）を XIAO にはんだ付け → ソケット（メス）に差す → そのまま基板に差して、ソケットの足を基板にはんだ付け。位置がずれない。",
              "- はんだ付けが終わったら、通電の前に `docs/bringup_plan.md` の HG-K-04（導通・短絡の確認）を行う。", ""]
    (ROOT / "docs" / "assembly_guide.md").write_text(chr(10).join(lines), encoding="utf-8", newline=chr(10))
    print("MD: docs/assembly_guide.md")


if __name__ == "__main__":
    main()
