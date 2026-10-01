#!/usr/bin/env python3
"""Stage 4: 自動配線。システムの Python（numpy + scipy）で実行する。

    python tools/route.py [--order name1,name2,...] [--attempts 6] [--out docs/routes.json]

入力  docs/placement_geometry.json（gen_pcb.py が作る: 外形・ランド・ネット）
出力  docs/routes.json（トラック・ビア。tools/apply_routes.py が KiCad の基板に書き込む）

方法: 0.0635 mm の格子（XIAO のピン列の 2.54 mm = 40 マス、ピンのすきま中央が格子点に乗る）に基板を切り、
      ネットごとに「すでに配線した銅」を障害物（クリアランス 0.2 + 配線幅/2 だけふくらませる）として、
      Dijkstra（scipy）で最短経路を探す。2 層（F.Cu / B.Cu）、層の乗り換えはビア（コスト大）か、そのネットのスルーホールのランド。
      幅の太いネットから順に、通らなければ細い幅にして再試行する。通らなかったネットを先頭に移して全体をやり直す。
GND は配線せず、両面のベタ（apply_routes.py）に任せる。表面実装の GND ランドには、近くにビアを 1 つ打つ（短い引き出し線つき）。
"""
import argparse
import json
import math
import pathlib
import sys
import time

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

ROOT = pathlib.Path(__file__).resolve().parent.parent
G = 0.0635                    # 格子 [mm]
G_NM = 63500
CLR = 0.2                     # 銅どうしのクリアランス
EDGE_CLR = 0.5                # 銅と基板の縁
HOLE_CLR = 0.25               # 銅と穴（取付穴）
VIA_D, VIA_DRILL = 0.6, 0.3
EPS = 0.008                   # 格子の量子化の余裕
CLASSES = [0.2, 0.25, 0.3, 0.4, 0.5, 0.6]
VIA_COST = 45.0               # ビア 1 つ = 格子 45 マス分（約 2.9 mm）
THRU_COST = 1.0               # スルーホールのランドで層を乗り換えるコスト
B_BIAS = 1.06                 # 裏面を少しだけ高く（表面を優先）
SQ2 = math.sqrt(2.0)

# (ネット名, 試す配線幅)。上から順に配線する（太い・重要なものを先に）
DEFAULT_ORDER = [
    ("/LEDA_L", [0.4, 0.3]), ("/LEDK_L", [0.4, 0.3]), ("/SENSE_L", [0.4, 0.3]),
    ("Net-(SJ1-A)", [0.4, 0.3]), ("Net-(SJ1-B)", [0.4, 0.3]),
    ("/LEDA_R", [0.4, 0.3]), ("/LEDK_R", [0.4, 0.3]), ("/SENSE_R", [0.4, 0.3]),
    ("Net-(SJ2-A)", [0.4, 0.3]), ("Net-(SJ2-B)", [0.4, 0.3]),
    ("+5V", [0.5, 0.4, 0.3]),
    ("/SDA", [0.25, 0.2]), ("/SCL", [0.25, 0.2]),
    ("/XSHUT_L", [0.25, 0.2]), ("/XSHUT_R", [0.25, 0.2]),
    ("+3V3", [0.5, 0.4, 0.3, 0.25, 0.2]),
    ("/LED_PWM_L", [0.25, 0.2]), ("/LED_PWM_R", [0.25, 0.2]),
    ("/GATE_L", [0.25, 0.2]), ("/GATE_R", [0.25, 0.2]),
    ("/D8_GPIO7", [0.25, 0.2]), ("/D9_GPIO8", [0.25, 0.2]),
    ("/TOF_L_INT", [0.25, 0.2]), ("/TOF_R_INT", [0.25, 0.2]),
]
GND_NET = "GND"
DIRS8 = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)]


class Router:
    def __init__(self, geo):
        self.geo = geo
        self.W, self.H, self.CR = geo["W"], geo["H"], geo["CR"]
        u1 = next(f for f in geo["fps"] if f["ref"] == "U1")
        ax, ay = u1["pads"][0]["c"]
        self.ox_nm = round(ax * 1e6) % G_NM
        self.oy_nm = round(ay * 1e6) % G_NM
        self.OX, self.OY = self.ox_nm / 1e6, self.oy_nm / 1e6
        self.NX = int((self.W - self.OX) / G) + 1
        self.NY = int((self.H - self.OY) / G) + 1
        self.NXY = self.NX * self.NY
        self.xs = self.OX + G * np.arange(self.NX)
        self.ys = self.OY + G * np.arange(self.NY)
        self.X, self.Y = np.meshgrid(self.xs, self.ys, indexing="ij")
        self.owner = {c: np.full((2, self.NX, self.NY), -1, np.int16) for c in CLASSES}
        # 網の名前 → 番号、ランド一覧
        self.net_ids = {}
        self.pads = []           # dict(ref, n, net(id), kind, c, hw, hh, thru, npth)
        for f in geo["fps"]:
            for p in f["pads"]:
                name = p["net"]
                nid = -1
                if name:
                    nid = self.net_ids.setdefault(name, len(self.net_ids))
                self.pads.append(dict(ref=f["ref"], n=p["n"], net=nid, name=name, kind=p.get("kind", "rect"), c=tuple(p["bc"]),
                                      hw=p["w"] / 2, hh=p["h"] / 2, thru=p["thru"], npth=p["npth"], poly=p.get("poly")))
        self.tracks = []         # dict(net, layer, w, a(x,y), b(x,y))  配線済み
        self.vias = []
        self.padzone = np.zeros((self.NX, self.NY), bool)   # ビアを置けない（ランドに近い）セル
        self.smd_cover = np.zeros((self.NX, self.NY), bool)
        self._paint_static()

    # ------------------------------------------------------------------ 距離
    def _win(self, xmin, xmax, ymin, ymax):
        i0 = max(0, int(math.floor((xmin - self.OX) / G)))
        i1 = min(self.NX, int(math.ceil((xmax - self.OX) / G)) + 1)
        j0 = max(0, int(math.floor((ymin - self.OY) / G)))
        j1 = min(self.NY, int(math.ceil((ymax - self.OY) / G)) + 1)
        return i0, i1, j0, j1

    @staticmethod
    def _dist(shape, X, Y):
        k = shape[0]
        if k == "rect":
            _, cx, cy, hw, hh = shape
            return np.hypot(np.maximum(np.abs(X - cx) - hw, 0), np.maximum(np.abs(Y - cy) - hh, 0))
        if k == "circle":
            _, cx, cy, r = shape
            return np.maximum(np.hypot(X - cx, Y - cy) - r, 0)
        if k == "poly":
            pts = shape[1]
            d = np.full(X.shape, np.inf)
            inside = np.zeros(X.shape, bool)
            n = len(pts)
            for a in range(n):
                x1, y1 = pts[a]
                x2, y2 = pts[(a + 1) % n]
                dx, dy = x2 - x1, y2 - y1
                L2 = dx * dx + dy * dy
                tt = np.clip(((X - x1) * dx + (Y - y1) * dy) / L2, 0, 1) if L2 else 0
                d = np.minimum(d, np.hypot(X - (x1 + tt * dx), Y - (y1 + tt * dy)))
                if dy:
                    inside ^= ((y1 > Y) != (y2 > Y)) & (X < (x2 - x1) * (Y - y1) / dy + x1)
            return np.where(inside, 0.0, d)
        # seg: 線分（太さ 2*hw）
        _, x1, y1, x2, y2, hw = shape
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        if L2 == 0:
            return np.maximum(np.hypot(X - x1, Y - y1) - hw, 0)
        t = np.clip(((X - x1) * dx + (Y - y1) * dy) / L2, 0, 1)
        return np.maximum(np.hypot(X - (x1 + t * dx), Y - (y1 + t * dy)) - hw, 0)

    @staticmethod
    def _bbox(shape):
        k = shape[0]
        if k == "rect":
            _, cx, cy, hw, hh = shape
            return cx - hw, cx + hw, cy - hh, cy + hh
        if k == "circle":
            _, cx, cy, r = shape
            return cx - r, cx + r, cy - r, cy + r
        if k == "poly":
            xs = [q[0] for q in shape[1]]
            ys = [q[1] for q in shape[1]]
            return min(xs), max(xs), min(ys), max(ys)
        _, x1, y1, x2, y2, hw = shape
        return min(x1, x2) - hw, max(x1, x2) + hw, min(y1, y2) - hw, max(y1, y2) + hw

    def mark(self, shape, layers, net, base=CLR, hard=False):
        """障害物 shape（net は番号。-1 = ネットなし）を、各幅クラスの owner にふくらませて書く。"""
        xmin, xmax, ymin, ymax = self._bbox(shape)
        for c in CLASSES:
            r = base + c / 2 + EPS
            i0, i1, j0, j1 = self._win(xmin - r, xmax + r, ymin - r, ymax + r)
            if i0 >= i1 or j0 >= j1:
                continue
            d = self._dist(shape, self.X[i0:i1, j0:j1], self.Y[i0:i1, j0:j1])
            m = d < r
            for l in layers:
                sub = self.owner[c][l, i0:i1, j0:j1]
                if hard or net < 0:
                    sub[m] = -2
                else:
                    cur = sub[m]
                    sub[m] = np.where(cur == -1, net, np.where(cur == net, net, -2))

    def _paint_static(self):
        W, H, CR = self.W, self.H, self.CR
        # 基板の縁（角 R つきの長方形）: 縁から EDGE_CLR + c/2 以内は銅を置けない
        cx, cy = W / 2, H / 2
        qx = np.abs(self.X - cx) - (W / 2 - CR)
        qy = np.abs(self.Y - cy) - (H / 2 - CR)
        sd = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - CR
        for c in CLASSES:
            blocked = (-sd) < (EDGE_CLR + c / 2 + EPS)
            self.owner[c][0][blocked] = -2
            self.owner[c][1][blocked] = -2
        # ランド
        for p in self.pads:
            layers = (0, 1) if p["thru"] else (0,)
            if p["npth"]:                                   # 取付穴: 銅なし。穴のふちからの距離
                shape = ("circle", p["c"][0], p["c"][1], p["hw"])
                self.mark(shape, (0, 1), -1, base=max(CLR, HOLE_CLR), hard=True)
                continue
            shape = self.pad_shape(p)
            self.mark(shape, layers, p["net"])
            # ビアはランドの上・すぐ脇に置かない（自分のネットのランドでも）
            xmin, xmax, ymin, ymax = self._bbox(shape)
            r = VIA_D / 2 + 0.1
            i0, i1, j0, j1 = self._win(xmin - r, xmax + r, ymin - r, ymax + r)
            d = self._dist(shape, self.X[i0:i1, j0:j1], self.Y[i0:i1, j0:j1])
            self.padzone[i0:i1, j0:j1] |= d < r

    # ------------------------------------------------------------------ 経路探索
    @staticmethod
    def pad_shape(p):
        if p.get("poly"):
            return ("poly", p["poly"])
        if p["kind"] in ("circle", "oval") and abs(p["hw"] - p["hh"]) < 1e-6:
            return ("circle", p["c"][0], p["c"][1], p["hw"])
        return ("rect", p["c"][0], p["c"][1], p["hw"], p["hh"])

    def passable(self, net, w):
        o = self.owner[w]
        return [(o[0] == -1) | (o[0] == net), (o[1] == -1) | (o[1] == net)]

    def via_ok(self, net):
        pv = self.passable(net, 0.6)
        return pv[0] & pv[1] & ~self.padzone

    def own_thru(self, net):
        m = np.zeros((self.NX, self.NY), bool)
        for p in self.pads:
            if p["net"] == net and p["thru"] and not p["npth"]:
                i0, i1, j0, j1 = self._win(p["c"][0] - p["hw"], p["c"][0] + p["hw"], p["c"][1] - p["hh"], p["c"][1] + p["hh"])
                m[i0:i1, j0:j1] |= self._inside(p, i0, i1, j0, j1)
        return m

    def _inside(self, p, i0, i1, j0, j1):
        X, Y = self.X[i0:i1, j0:j1], self.Y[i0:i1, j0:j1]
        shape = self.pad_shape(p)
        if shape[0] == "poly":
            return self._dist(shape, X, Y) == 0
        if shape[0] == "circle":
            return np.hypot(X - p["c"][0], Y - p["c"][1]) <= p["hw"]
        return (np.abs(X - p["c"][0]) <= p["hw"]) & (np.abs(Y - p["c"][1]) <= p["hh"])

    def pad_cells(self, p, passl):
        """ランド内でそのネットが通れるセルの (layer, i, j) の配列。"""
        i0, i1, j0, j1 = self._win(p["c"][0] - p["hw"], p["c"][0] + p["hw"], p["c"][1] - p["hh"], p["c"][1] + p["hh"])
        ins = self._inside(p, i0, i1, j0, j1)
        out = []
        for l in ((0, 1) if p["thru"] else (0,)):
            m = ins & passl[l][i0:i1, j0:j1]
            ii, jj = np.nonzero(m)
            out.append(np.stack([np.full(len(ii), l), ii + i0, jj + j0], axis=1))
        return np.concatenate(out) if out else np.zeros((0, 3), int)

    def flat(self, cells):
        return cells[:, 0] * self.NXY + cells[:, 1] * self.NY + cells[:, 2]

    def build_graph(self, net, passl, via_ok, thru, allow_via=True):
        NX, NY = self.NX, self.NY
        N = 2 * self.NXY
        idx = np.arange(N).reshape(2, NX, NY)
        rows, cols, data = [], [], []

        def add(a, b, wt):
            rows.append(a)
            cols.append(b)
            data.append(np.full(len(a), wt))
            rows.append(b)
            cols.append(a)
            data.append(np.full(len(a), wt))

        for l in (0, 1):
            P = passl[l]
            f = B_BIAS if l else 1.0
            ix = idx[l]
            m = P[:-1, :] & P[1:, :]
            add(ix[:-1, :][m], ix[1:, :][m], f)
            m = P[:, :-1] & P[:, 1:]
            add(ix[:, :-1][m], ix[:, 1:][m], f)
            m = P[:-1, :-1] & P[1:, 1:] & P[1:, :-1] & P[:-1, 1:]
            add(ix[:-1, :-1][m], ix[1:, 1:][m], f * SQ2)
            m = P[:-1, 1:] & P[1:, :-1] & P[:-1, :-1] & P[1:, 1:]
            add(ix[:-1, 1:][m], ix[1:, :-1][m], f * SQ2)
        both = passl[0] & passl[1]
        if allow_via:
            m = via_ok & both
            add(idx[0][m], idx[1][m], VIA_COST)
        m = thru & both
        add(idx[0][m], idx[1][m], THRU_COST)
        r = np.concatenate(rows)
        c = np.concatenate(cols)
        d = np.concatenate(data)
        return csr_matrix((d, (r, c)), shape=(N, N))

    def moves(self, node, passl, via_ok, thru):
        """1 つの節から行ける節（build_graph と同じ規則）: [(節, コスト, 方向番号)]"""
        l, i, j = node
        out = []
        P = passl[l]
        f = B_BIAS if l else 1.0
        for k, (dx, dy) in enumerate(DIRS8):
            i2, j2 = i + dx, j + dy
            if not (0 <= i2 < self.NX and 0 <= j2 < self.NY) or not P[i2, j2]:
                continue
            if dx and dy and not (P[i2, j] and P[i, j2]):
                continue
            out.append(((l, i2, j2), f * (SQ2 if (dx and dy) else 1.0), k))
        both = passl[0][i, j] and passl[1][i, j]
        if both:
            if via_ok[i, j]:
                out.append(((1 - l, i, j), VIA_COST, 8))
            elif thru[i, j]:
                out.append(((1 - l, i, j), THRU_COST, 8))
        elif False:
            pass
        return out

    def find_path(self, net, w, tree_cells, target_cells, passl, via_ok, thru, allow_via=True):
        """tree_cells（出発点の集合）から target_cells（目的の集合）の一番近いものへの最短経路。見つからなければ None。"""
        graph = self.build_graph(net, passl, via_ok, thru, allow_via)
        tflat = np.unique(self.flat(target_cells))
        D = dijkstra(graph, directed=True, indices=tflat, min_only=True)
        sflat = self.flat(tree_cells)
        ds = D[sflat]
        k = int(np.argmin(ds))
        if not np.isfinite(ds[k]):
            return None
        cur = tuple(int(v) for v in tree_cells[k])
        path = [cur]
        prev_dir = None
        tset = set(int(v) for v in tflat)
        guard = 0
        while self.flat(np.array([cur]))[0] not in tset:
            guard += 1
            if guard > 200000:
                return None
            u = cur[0] * self.NXY + cur[1] * self.NY + cur[2]
            du = D[u]
            best = None
            for nb, cost, kdir in self.moves(cur, passl, via_ok, thru):
                v = nb[0] * self.NXY + nb[1] * self.NY + nb[2]
                if abs(D[v] + cost - du) < 1e-6:
                    pri = (0 if kdir == prev_dir else 1, 0 if kdir < 4 else 1, kdir)     # 直進 > 縦横 > 斜め
                    if best is None or pri < best[0]:
                        best = (pri, nb, kdir)
            if best is None:
                return None
            _, cur, prev_dir = best
            path.append(cur)
        return path

    # ------------------------------------------------------------------ 配線の登録
    def add_path(self, net, w, path, thru):
        """経路を銅として登録（障害物にする）。層の乗り換え点にビアを置く。"""
        for a, b in zip(path[:-1], path[1:]):
            if a[0] != b[0]:
                continue
            ax, ay = self.xs[a[1]], self.ys[a[2]]
            bx, by = self.xs[b[1]], self.ys[b[2]]
            self.mark(("seg", ax, ay, bx, by, w / 2), (a[0],), net)
        for a, b in zip(path[:-1], path[1:]):
            if a[0] != b[0]:
                x, y = self.xs[a[1]], self.ys[a[2]]
                if not thru[a[1], a[2]]:
                    self.mark(("circle", x, y, VIA_D / 2), (0, 1), net)

    def segmentize(self, net, wpaths, thru):
        """経路 [(幅, 経路)] → (トラック, ビア)。ほかの経路の出入りする節（接合点）では線を切る。"""
        junction = set()
        for _, pth in wpaths:
            junction.add(pth[0])
            junction.add(pth[-1])
        tracks, vias = [], []
        for w, pth in wpaths:
            seg_start = pth[0]
            prev = pth[0]
            pdir = None
            for nd in pth[1:]:
                if nd[0] != prev[0]:                              # 層の乗り換え
                    if prev != seg_start:
                        tracks.append((net, prev[0], w, seg_start, prev))
                    if not thru[prev[1], prev[2]]:
                        vias.append((net, prev[1], prev[2]))
                    seg_start = nd
                    prev = nd
                    pdir = None
                    continue
                d = (nd[1] - prev[1], nd[2] - prev[2])
                if pdir is not None and (d != pdir or (prev in junction and prev != seg_start)):
                    tracks.append((net, prev[0], w, seg_start, prev))
                    seg_start = prev
                pdir = d
                prev = nd
            if prev != seg_start:
                tracks.append((net, prev[0], w, seg_start, prev))
        return tracks, vias


def route_all(rt, order, verbose=True):
    """order の順に配線。返り値: (tracks, vias, failures)。"""
    # 状態を作り直す（owner を初期化して静的な障害物を描き直す）
    for c in CLASSES:
        rt.owner[c][:] = -1
    rt.padzone[:] = False
    rt._paint_static()
    all_tracks, all_vias, fails, report = [], [], [], []
    for name, widths in order:
        if name not in rt.net_ids:
            continue
        net = rt.net_ids[name]
        pads = [p for p in rt.pads if p["net"] == net]
        if len(pads) < 2:
            continue
        thru = rt.own_thru(net)
        via_ok = rt.via_ok(net)
        anchor = sorted(range(len(pads)), key=lambda i: (not pads[i]["thru"], i))[0]
        passl0 = rt.passable(net, widths[0])
        tree = rt.pad_cells(pads[anchor], passl0)
        if len(tree) == 0:
            fails.append((name, "anchor pad has no free cell"))
            continue
        remaining = [i for i in range(len(pads)) if i != anchor]
        paths, chosen_w = [], []
        t0 = time.time()
        while remaining:
            done = False
            for w in widths:
                passl = rt.passable(net, w)
                tcells_list = [rt.pad_cells(pads[i], passl) for i in remaining]
                tcells_all = np.concatenate([c for c in tcells_list if len(c)]) if any(len(c) for c in tcells_list) else np.zeros((0, 3), int)
                if len(tcells_all) == 0:
                    continue
                # 出発点: これまでの木（現在の幅でも通れるセルだけ）
                tr_ok = tree[passl[0][tree[:, 1], tree[:, 2]] & (tree[:, 0] == 0) | passl[1][tree[:, 1], tree[:, 2]] & (tree[:, 0] == 1)]
                if len(tr_ok) == 0:
                    continue
                path = rt.find_path(net, w, tr_ok, tcells_all, passl, via_ok, thru)
                if path is None:
                    continue
                end = path[-1]
                hit = None
                for i, c in zip(remaining, tcells_list):
                    if len(c) and np.any((c[:, 0] == end[0]) & (c[:, 1] == end[1]) & (c[:, 2] == end[2])):
                        hit = i
                        break
                rt.add_path(net, w, path, thru)
                paths.append((w, path))
                tree = np.concatenate([tree, np.array(path), tcells_list[remaining.index(hit)]])
                remaining.remove(hit)
                done = True
                break
            if not done:
                fails.append((name, f"unreached: {[pads[i]['ref'] + '.' + pads[i]['n'] for i in remaining]}"))
                break
        # トラックへ
        t, v = rt.segmentize(net, paths, thru)
        all_tracks += t
        all_vias += v
        if verbose:
            ws = sorted(set(w for w, _ in paths))
            print(f"  {name:14s} pads={len(pads):2d} paths={len(paths):2d} widths={ws} {time.time() - t0:5.1f}s" + (" FAIL" if any(f[0] == name for f in fails) else ""), flush=True)
    return all_tracks, all_vias, fails


def gnd_stubs(rt, tracks, vias):
    """GND の表面実装ランドごとに、近くへビアを 1 つ（短い引き出し線つき）。ベタ（両面）につなぐ。"""
    net = rt.net_ids[GND_NET]
    out_t, out_v, fails = [], [], []
    for p in rt.pads:
        if p["net"] != net or p["thru"] or p["npth"]:
            continue
        done = False
        for w in (0.4, 0.3, 0.25, 0.2):
            passl = rt.passable(net, w)
            via_ok = rt.via_ok(net)
            cells = rt.pad_cells(p, passl)
            if len(cells) == 0:
                continue
            tg = np.stack([np.zeros(int(via_ok.sum()), int), *np.nonzero(via_ok)], axis=1)          # 表面の、ビアを置ける全セル
            thru = np.zeros((rt.NX, rt.NY), bool)
            path = rt.find_path(net, w, cells, tg, passl, via_ok, thru, allow_via=False)
            if path is None:
                continue
            rt.add_path(net, w, path, thru)
            rt.mark(("circle", rt.xs[path[-1][1]], rt.ys[path[-1][2]], VIA_D / 2), (0, 1), net)
            t, v = rt.segmentize(net, [(w, path)], thru)
            out_t += t
            out_v.append((net, path[-1][1], path[-1][2]))
            done = True
            break
        if not done:
            fails.append((GND_NET, f"{p['ref']}.{p['n']}"))
    return out_t, out_v, fails


def to_json(rt, tracks, vias):
    names = {v: k for k, v in rt.net_ids.items()}

    def nm(i, j):
        return [rt.ox_nm + G_NM * i, rt.oy_nm + G_NM * j]

    out = dict(grid_nm=G_NM, ox_nm=rt.ox_nm, oy_nm=rt.oy_nm, W=rt.W, H=rt.H, tracks=[], vias=[])
    for net, layer, w, a, b in tracks:
        out["tracks"].append(dict(net=names[net], layer="F.Cu" if layer == 0 else "B.Cu", w=w, a=nm(a[1], a[2]), b=nm(b[1], b[2])))
    seen = set()
    for net, i, j in vias:
        if (i, j) in seen:
            continue
        seen.add((i, j))
        out["vias"].append(dict(net=names[net], at=nm(i, j), d=VIA_D, drill=VIA_DRILL))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempts", type=int, default=6)
    ap.add_argument("--geometry", default=str(ROOT / "docs" / "placement_geometry.json"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "routes.json"))
    ap.add_argument("--order", default=None, help="先頭に置くネット名（カンマ区切り）")
    args = ap.parse_args()
    geo = json.loads(pathlib.Path(args.geometry).read_text(encoding="utf-8"))
    rt = Router(geo)
    print(f"grid {rt.NX} x {rt.NY} (G={G} mm), nets {len(rt.net_ids)}, pads {len(rt.pads)}")
    order = list(DEFAULT_ORDER)
    if args.order:
        front = args.order.split(",")
        order = [o for o in order if o[0] in front] + [o for o in order if o[0] not in front]
    best = None
    for attempt in range(args.attempts):
        print(f"attempt {attempt + 1}: order = {[o[0] for o in order]}")
        tracks, vias, fails = route_all(rt, order)
        print(f"  -> tracks {len(tracks)}, vias {len(vias)}, failures {len(fails)}: {fails}")
        if best is None or len(fails) < len(best[2]):
            best = (tracks, vias, fails, order)
        if not fails:
            break
        bad = [f[0] for f in fails]
        order = [o for o in order if o[0] in bad] + [o for o in order if o[0] not in bad]
    tracks, vias, fails, order = best
    # 最良の順序でもう一度（rt の状態を最良のものにそろえて GND の引き出し線を足す）
    tracks, vias, fails = route_all(rt, order, verbose=False)
    gt, gv, gf = gnd_stubs(rt, tracks, vias)
    tracks += gt
    vias += gv
    print(f"GND stubs: {len(gv)} vias, failures {gf}")
    js = to_json(rt, tracks, vias)
    js["failures"] = [list(f) for f in fails] + [list(f) for f in gf]
    pathlib.Path(args.out).write_text(json.dumps(js, ensure_ascii=False, indent=1), encoding="utf-8")
    tl = {}
    for t in js["tracks"]:
        tl[t["w"]] = tl.get(t["w"], 0) + math.dist(t["a"], t["b"]) / 1e6
    print("track length by width [mm]:", {k: round(v, 1) for k, v in sorted(tl.items())}, "vias:", len(js["vias"]))
    print("failures:", js["failures"] if js["failures"] else "none")
    return 0 if not js["failures"] else 1


if __name__ == "__main__":
    sys.exit(main())
