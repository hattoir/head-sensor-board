"""KiCad の S 式（.kicad_sym / .kicad_sch / .kicad_mod）を読む・書く最小限のコード（標準ライブラリだけ）。

- parse(text) -> ノード（list）。引用符つき文字列は Q、裸の語は str で区別する（書き戻しで引用符を保つため）。
- dump(node) -> KiCad と同じ「タブ字下げ」の文字列。
- SymbolLibrary: .kicad_sym からシンボルを取り出し、回路図の lib_symbols 用テキストとピン座標を返す。
"""
import pathlib
import re


class Q(str):
    """引用符つきの文字列"""


_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)


def parse(text):
    pos, stack, root = 0, [], None
    cur = None
    while True:
        m = _TOKEN.match(text, pos)
        if not m:
            break
        pos = m.end()
        op, cl, qs, atom = m.groups()
        if op:
            node = []
            if cur is not None:
                cur.append(node)
                stack.append(cur)
            else:
                root = node
            cur = node
        elif cl:
            cur = stack.pop() if stack else None
            if cur is None:
                break
        elif qs is not None:
            cur.append(Q(qs))
        elif atom is not None:
            cur.append(atom)
    return root


def _atom(x):
    if isinstance(x, Q):
        return '"' + str(x) + '"'
    return str(x)


def dump(node, depth=0):
    """リストだけを子に持たない要素は 1 行、持つ要素は頭の語を 1 行目に、子を次の行に書く。"""
    tab = "\t" * depth
    if not any(isinstance(c, list) for c in node):
        return tab + "(" + " ".join(_atom(c) for c in node) + ")"
    # pts のような (xy ..) が並ぶ行はまとめる
    if node and node[0] == "pts" and all(isinstance(c, list) and c and c[0] == "xy" for c in node[1:]):
        return tab + "(pts " + " ".join("(" + " ".join(_atom(c) for c in xy) + ")" for xy in node[1:]) + ")"
    head = [c for c in node if not isinstance(c, list)]
    # 先頭の連続する原子だけを 1 行目に置く
    i = 0
    while i < len(node) and not isinstance(node[i], list):
        i += 1
    lines = [tab + "(" + " ".join(_atom(c) for c in node[:i])]
    for c in node[i:]:
        if isinstance(c, list):
            lines.append(dump(c, depth + 1))
        else:
            lines.append("\t" * (depth + 1) + _atom(c))
    lines.append(tab + ")")
    return "\n".join(lines)


def find_all(node, name):
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def find(node, name):
    r = find_all(node, name)
    return r[0] if r else None


class SymbolLibrary:
    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.tree = parse(self.path.read_text(encoding="utf-8"))
        self.symbols = {str(s[1]): s for s in find_all(self.tree, "symbol")}

    def get(self, name):
        return self.symbols[name]

    def lib_symbol_text(self, nick, name, depth=1):
        """回路図の lib_symbols に入れるテキスト（最上位の名前だけ 'Nick:Name' にする）。"""
        import copy
        s = copy.deepcopy(self.symbols[name])
        s[1] = Q(f"{nick}:{name}")
        return dump(s, depth)

    def pins(self, name):
        """{ピン番号: dict(x, y, angle, name, type)} 単位 1・図形体 1 と共通部（_0_）のピン。"""
        s = self.symbols[name]
        out = {}
        for sub in find_all(s, "symbol"):
            sname = str(sub[1])
            m = re.search(r"_(\d+)_(\d+)$", sname)
            unit = int(m.group(1)) if m else 0
            if unit not in (0, 1):
                continue
            for p in find_all(sub, "pin"):
                at = find(p, "at")
                num = str(find(p, "number")[1])
                out[num] = dict(x=float(at[1]), y=float(at[2]), angle=float(at[3]), length=float(find(p, "length")[1]),
                                name=str(find(p, "name")[1]), type=str(p[1]))
        return out
