#!/usr/bin/env python3
"""すべての検査を順に回して、1 つの表にする（何も書き換えない。発注の前・基板を直したあとに実行する）。

    python tools/run_all_checks.py [--no-gerber]

  1. ERC（プロジェクトの設定どおり、全重大度）                kicad-cli
  2. DRC（回路図との対応つき、全重大度）                       kicad-cli
  3. ネットリストの照合・フットプリントのパッド番号の照合       tools/check_netlist.py
  4. J1/J2 のネット・パッド・刻印の照合 + 刻印のすきま           tools/check_board.py（KiCad の Python）
  5. 発注先の公開仕様との照合（JLCPCB の標準の文字高さ以外が通る）  tools/check_fab_rules.py（KiCad の Python）
  6. gerbers/ が今の基板から作り直したものと同じ図形か（古くなっていない） tools/compare_gerbers.py --current（gerbonara）
  7. gerbers/ の ZIP を読み直して基板と照合                     tools/verify_gerbers.py（gerbonara）
gerbonara が無ければ 6・7 は SKIP（pip install gerbonara）。終了コード: 1 つでも FAIL なら 1（5 の PASS* = JLCPCB の標準の文字高さだけ未達、は許す）。
"""
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
KC = "C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"
KPY = "C:/Program Files/KiCad/10.0/bin/python.exe"


def run(cmd, **kw):
    r = subprocess.run([str(c) for c in cmd], cwd=ROOT, capture_output=True, **kw)
    return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace") if isinstance(r.stdout, bytes) else (r.stdout + r.stderr)


def has_gerbonara():
    try:
        import gerbonara  # noqa: F401
        return True
    except ImportError:
        return False


def main():
    no_gerber = "--no-gerber" in sys.argv or not has_gerbonara()
    rows = []
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        rc, _ = run([KC, "sch", "erc", "--severity-all", "--exit-code-violations", "--output", d / "erc.txt", ROOT / "head-sensor-board.kicad_sch"])
        rows.append(("ERC", "PASS" if rc == 0 else "FAIL", "違反 0" if rc == 0 else "違反あり（docs/erc_report.txt を作り直して確認）"))
        rc, _ = run([KC, "pcb", "drc", "--schematic-parity", "--severity-all", "--exit-code-violations", "--output", d / "drc.txt", ROOT / "head-sensor-board.kicad_pcb"])
        txt = (d / "drc.txt").read_text(encoding="utf-8", errors="replace") if (d / "drc.txt").exists() else ""
        found = [ln for ln in txt.splitlines() if ln.startswith("** Found")]
        rows.append(("DRC（回路図との対応つき）", "PASS" if rc == 0 else "FAIL", "; ".join(x.strip("* ") for x in found)))
    rc, out = run([sys.executable, "tools/check_netlist.py"])
    rows.append(("ネットリスト・パッド番号", "PASS" if rc == 0 and "ALL NETS MATCH" in out else "FAIL", next((ln for ln in out.splitlines() if "RESULT" in ln), "")))
    rc, out = run([KPY, "tools/check_board.py"], env=dict(__import__("os").environ, PYTHONIOENCODING="utf-8"))
    rows.append(("J1/J2 の整合・刻印のすきま", "PASS" if rc == 0 else "FAIL", next((ln for ln in out.splitlines() if ln.startswith("RESULT")), "")))
    rc, out = run([KPY, "tools/check_fab_rules.py"], env=dict(__import__("os").environ, PYTHONIOENCODING="utf-8"))
    star = "FAIL*" in out                                  # 上位オプション（JLCPCB の高精度の文字）なら通る未達
    if rc != 0:
        rows.append(("発注先の公開仕様（4 社）", "FAIL", "FAIL あり（python tools/check_fab_rules.py で確認）"))
    elif star:
        rows.append(("発注先の公開仕様（4 社）", "PASS*", "JLCPCB の標準の文字高さ 1.0 mm だけ未達（高精度の文字オプションなら可）。ほかの 3 社は PASS"))
    else:
        rows.append(("発注先の公開仕様（4 社）", "PASS", "全社 PASS"))
    if no_gerber:
        rows.append(("gerbers/ が最新", "SKIP", "gerbonara が無い（pip install gerbonara）"))
        rows.append(("gerbers/ の読み直し", "SKIP", "同上"))
    else:
        rc, out = run([sys.executable, "tools/compare_gerbers.py", "--current"], env=dict(__import__("os").environ, PYTHONIOENCODING="utf-8"))
        rows.append(("gerbers/ が最新（作り直した図形と同じ）", "PASS" if rc == 0 else "FAIL", next((ln for ln in out.splitlines() if ln.startswith("RESULT")), "")))
        rc, out = run([sys.executable, "tools/verify_gerbers.py"], env=dict(__import__("os").environ, PYTHONIOENCODING="utf-8"))
        rows.append(("gerbers/ の ZIP の読み直し", "PASS" if rc == 0 else "FAIL", next((ln for ln in out.splitlines() if ln.startswith("RESULT")), "")))
    w = max(len(r[0]) for r in rows)
    for name, st, note in rows:
        print(f"{st:6s} {name:{w}s}  {note}")
    bad = [r for r in rows if r[1] == "FAIL"]
    print("RESULT:", "すべて通った" if not bad else f"{len(bad)} 件 FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
