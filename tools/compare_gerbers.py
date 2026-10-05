#!/usr/bin/env python3
"""2 つの製造データ（フォルダ、ZIP、または git の ref）を、図形として比べる。gerbonara が要る（検査にだけ使う）。

    python tools/compare_gerbers.py A B       A, B = フォルダ / ZIP / git の ref（例: HEAD, 4973aba）
    python tools/compare_gerbers.py --current  今の基板から作り直したガーバーが、gerbers/ と同じ図形か（古くなっていないか）

層ごとに、図形（種類と外接する四角）を順序に関係なく数え比べる。KiCad は書き出すたびに図形の並びやアパーチャ番号が変わるので、
ファイルの文字列を比べると、同じ形でも「違う」と出る。ドリルは (x, y, 径, めっき)。
出力: 層ごとの「A にだけ / B にだけある図形の数」。終了コード: 差があれば 1。
"""
import pathlib
import subprocess
import sys
import tempfile
import warnings
from collections import Counter

warnings.simplefilter("ignore")
from gerbonara import LayerStack          # noqa: E402
from gerbonara.utils import MM            # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAB_EXT = (".gtl", ".gbl", ".gts", ".gbs", ".gto", ".gbo", ".gtp", ".gm1", ".drl", ".gbrjob")


def load(spec, tmp):
    p = pathlib.Path(spec)
    if p.exists():
        return LayerStack.open(str(p))
    out = pathlib.Path(tmp) / spec.replace("/", "_")                  # git の ref から gerbers/ のファイルを取り出す
    out.mkdir(parents=True, exist_ok=True)
    names = subprocess.run(["git", "ls-tree", "--name-only", spec, "gerbers/"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    for n in names:
        if n.lower().endswith(FAB_EXT):
            (out / pathlib.Path(n).name).write_bytes(subprocess.run(["git", "show", f"{spec}:{n}"], cwd=ROOT, capture_output=True, check=True).stdout)
    return LayerStack.open(str(out))


def sig(o):
    try:
        (x0, y0), (x1, y1) = o.bounding_box(MM)
    except Exception:
        return (type(o).__name__,)
    return (type(o).__name__, round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3))


def drills(st):
    out = []
    for f, plated in ((st.drill_pth, True), (st.drill_npth, False)):
        if f:
            out += [(round(o.x, 3), round(o.y, 3), round(o.aperture.diameter, 3), plated) for o in f.objects]
    return Counter(out)


def compare(sa, sb):
    diff = 0
    for key in sorted(set(sa.graphic_layers) | set(sb.graphic_layers)):
        if key not in sa.graphic_layers or key not in sb.graphic_layers:
            print(f"  {key}: 片方にしかない層")
            diff += 1
            continue
        a = Counter(sig(o) for o in sa.graphic_layers[key].objects)
        b = Counter(sig(o) for o in sb.graphic_layers[key].objects)
        oa, ob = sum((a - b).values()), sum((b - a).values())
        print(f"  {key[0]:10s} {key[1]:8s} 図形 {sum(a.values()):5d} / {sum(b.values()):5d}   A にだけ {oa:4d}  B にだけ {ob:4d}  {'SAME' if oa == ob == 0 else 'DIFF'}")
        diff += (oa != 0 or ob != 0)
    da, db = drills(sa), drills(sb)
    oa, ob = sum((da - db).values()), sum((db - da).values())
    print(f"  {'drill':19s} 穴   {sum(da.values()):5d} / {sum(db.values()):5d}   A にだけ {oa:4d}  B にだけ {ob:4d}  {'SAME' if oa == ob == 0 else 'DIFF'}")
    return diff + (oa != 0 or ob != 0)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        if sys.argv[1:] == ["--current"]:
            out = pathlib.Path(tmp) / "now"
            out.mkdir()
            sys.path.insert(0, str(ROOT / "tools"))
            import make_fabrication as mf
            mf.OUT = out
            mf.main()
            sa, sb = load(str(ROOT / "gerbers" / "head-sensor-board_gerbers.zip"), tmp), load(str(out / "head-sensor-board_gerbers.zip"), tmp)
        elif len(sys.argv) == 3:
            sa, sb = load(sys.argv[1], tmp), load(sys.argv[2], tmp)
        else:
            sys.exit(__doc__)
        d = compare(sa, sb)
    print("RESULT:", "同じ図形" if d == 0 else f"{d} 層に差")
    return 1 if d else 0


if __name__ == "__main__":
    sys.exit(main())
