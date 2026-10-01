#!/usr/bin/env python
"""Stage 4: docs/routes.json（tools/route.py の結果）を基板に書き込み、GND のベタ（両面）を作って塗りつぶす。
KiCad 同梱の Python で実行する:

    "C:/Program Files/KiCad/10.0/bin/python.exe" tools/apply_routes.py [--routes docs/routes.json] [--pcb head-sensor-board.kicad_pcb]

- 既存のトラック・ビア・ゾーンは消してから書く（何度実行しても同じ結果）。部品・外形・刻印はそのまま。
- GND のゾーン: F.Cu と B.Cu の両面、外形から 0.5 mm 内側まで。ランドへはサーマルリリーフ（スポーク 0.4 mm）。
"""
import argparse
import json
import pathlib

import pcbnew
from pcbnew import FromMM, VECTOR2I

ROOT = pathlib.Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("--routes", default=str(ROOT / "docs" / "routes.json"))
ap.add_argument("--pcb", default=str(ROOT / "head-sensor-board.kicad_pcb"))
ap.add_argument("--no-zones", action="store_true")
ap.add_argument("--edge-inset", type=float, default=0.5, help="ベタを外形から内側へ引く量 [mm]")
args = ap.parse_args()

routes = json.loads(pathlib.Path(args.routes).read_text(encoding="utf-8"))
board = pcbnew.LoadBoard(args.pcb)
W, H = routes["W"], routes["H"]
X0_NM, Y0_NM = round((297.0 - W) / 2.0 * 1e6), round((210.0 - H) / 2.0 * 1e6)


def pt(xy):
    return VECTOR2I(X0_NM + int(xy[0]), Y0_NM + int(xy[1]))


# 既存の配線・ゾーンを消す
for t in list(board.GetTracks()):
    board.Remove(t)
for z in list(board.Zones()):
    board.Remove(z)

LAYER = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}


def net_of(name):
    n = board.FindNet(name)
    if n is None:
        raise SystemExit(f"net not found: {name}")
    return n


for t in routes["tracks"]:
    tr = pcbnew.PCB_TRACK(board)
    tr.SetStart(pt(t["a"]))
    tr.SetEnd(pt(t["b"]))
    tr.SetWidth(FromMM(t["w"]))
    tr.SetLayer(LAYER[t["layer"]])
    tr.SetNet(net_of(t["net"]))
    board.Add(tr)

for v in routes["vias"]:
    via = pcbnew.PCB_VIA(board)
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetPosition(pt(v["at"]))
    try:
        via.SetWidth(FromMM(v["d"]))
    except TypeError:
        via.SetWidth(pcbnew.F_Cu, FromMM(v["d"]))            # KiCad 9 以降のパッドスタック版
    via.SetDrill(FromMM(v["drill"]))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(net_of(v["net"]))
    board.Add(via)

if not args.no_zones:
    gnd = net_of("GND")
    ins = args.edge_inset
    for layer in (pcbnew.B_Cu, pcbnew.F_Cu):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(gnd)
        z.SetAssignedPriority(0)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(FromMM(0.3))
        z.SetThermalReliefSpokeWidth(FromMM(0.4))
        z.SetMinThickness(FromMM(0.25))
        z.SetLocalClearance(FromMM(0.2))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        ol = z.Outline()
        ol.NewOutline()
        for x, y in ((ins, ins), (W - ins, ins), (W - ins, H - ins), (ins, H - ins)):
            ol.Append(X0_NM + FromMM(x), Y0_NM + FromMM(y))
        board.Add(z)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())

board.Save(args.pcb)
print(f"applied: {len(routes['tracks'])} tracks, {len(routes['vias'])} vias, zones {0 if args.no_zones else 2} -> {args.pcb}")
