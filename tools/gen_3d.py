#!/usr/bin/env python3
"""3D ビュー用の簡易モデル（箱の組み合わせ）を作る。標準ライブラリに 3D モデルが無い自作部品だけ。

    python tools/gen_3d.py        → 3dmodels/XIAO_ESP32S3_Sense_stack.wrl, 3dmodels/LED_NSSW157T.wrl

**見た目の確認用であって、寸法の根拠にはしない。**
  - XIAO: 2.54 mm ピッチ 1×7 メスソケット 2 本（高さ 8.5 mm は仮。購入品で確認する）、基板 21 × 17.8 × 1.2、USB-C シェル、
    Sense 拡張ボード（Seeed の DXF の外形 17.83 × 15.42。XIAO の USB-C と反対の端に載る。厚さと高さは仮。カメラ・microSD は作っていない）。
  - LED: NSSW157T の本体 3.0 × 1.4 × 0.52 mm（Nichia 仕様書の外形）。
単位は mm で書き、フットプリントの (scale 0.3937) で KiCad の VRML の単位（0.1 インチ）に合わせる。
座標はフットプリントと同じ向き（x 右、y はフットプリントの y と逆 = 上が +）。
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "3dmodels"


def box(x0, x1, y0, y1, z0, z1, rgb, transparency=0.0):
    pts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    coords = ", ".join(f"{x:.4f} {y:.4f} {z:.4f}" for x, y, z in pts)
    faces = "0,3,2,1,-1, 4,5,6,7,-1, 0,1,5,4,-1, 1,2,6,5,-1, 2,3,7,6,-1, 3,0,4,7,-1"
    r, g, b = rgb
    return (f"Shape {{\n appearance Appearance {{ material Material {{ diffuseColor {r} {g} {b} specularColor 0.3 0.3 0.3 transparency {transparency} }} }}\n"
            f" geometry IndexedFaceSet {{ coord Coordinate {{ point [ {coords} ] }} coordIndex [ {faces} ] solid FALSE }}\n}}\n")


def write(name, parts, comment):
    OUT.mkdir(parents=True, exist_ok=True)
    s = "#VRML V2.0 utf8\n# " + comment + "\n" + "".join(parts)
    (OUT / name).write_text(s, encoding="utf-8", newline="\n")


def main():
    # フットプリント座標（XIAO は USB-C が -y 側。モデルの y は符号を反転する）
    BLACK, PCB, SILVER, EXP = (0.08, 0.08, 0.09), (0.12, 0.12, 0.16), (0.78, 0.78, 0.8), (0.1, 0.35, 0.2)
    sock_h = 8.5                                             # ソケットの高さ（仮）
    parts = []
    for cx in (-7.62, 7.62):                                  # メスソケット 1×7（2.54 × 17.78）
        parts.append(box(cx - 1.27, cx + 1.27, -8.89, 8.89, 0.0, sock_h, BLACK))
    parts.append(box(-8.9, 8.9, -10.5, 10.5, sock_h, sock_h + 1.2, PCB))                      # XIAO の基板
    parts.append(box(-4.5, 4.5, 10.7 - 7.3, 10.7, sock_h + 1.2, sock_h + 1.2 + 3.2, SILVER))     # USB-C（上面側、-y が +y に反転）
    # Sense 拡張ボード: USB-C と反対の端（フットプリントの +y 側 = モデルの -y 側）。仮の厚さ・高さ
    z0 = sock_h + 1.2 + 1.5
    parts.append(box(-8.915, 8.915, -10.5, -10.5 + 15.42, z0, z0 + 1.0, EXP))
    write("XIAO_ESP32S3_Sense_stack.wrl", parts, "XIAO ESP32S3 Sense on 2 x 1x7 sockets (illustration only; heights assumed). mm units, use scale 0.3937")
    led = [box(-1.5, 1.5, -0.7, 0.7, 0.0, 0.52, (0.95, 0.95, 0.9)), box(-1.0, 1.0, -0.45, 0.45, 0.52, 0.53, (1.0, 0.9, 0.3))]
    write("LED_NSSW157T.wrl", led, "Nichia NSSW157T body 3.0 x 1.4 x 0.52 mm (illustration only). mm units, use scale 0.3937")
    print("ok:", sorted(p.name for p in OUT.glob("*.wrl")))


if __name__ == "__main__":
    main()
