#!/usr/bin/env python3
"""NSSW157T を XIAO の 3V3 だけで駆動したときの LED 電流と 3V3 の総負荷の計算。

表示するだけのスクリプト（回路図の注記・docs/spec.md の表の元）。標準ライブラリだけで動く。
    python tools/led_budget.py

入力値の出典（README §出典）:
  - Vf(80 mA) typ 3.1 V、Vf の範囲 2.8〜3.4 V (IF=80 mA)、IF max 150 mA … Nichia STS-DA1-1913 p.1-2  [原本]
  - Vf(10 mA) ≒ 2.73 V … 同 p.11 の VF-IF グラフの読み取り（"参考値・保証なし" と明記されている）
  - Vcc の幅 3.2〜3.4 V … 仮定（XIAO の 3V3 の精度は資料に記載なし）
  - MOSFET の Rds(on) 0.05 Ω … 仮定（候補部品の値。購入品の型番が決まったら置き換える）
"""

# ---- LED の Vf モデル: 10 mA と 80 mA の 2 点を通る直線（動作範囲 8〜40 mA では概ね妥当な近似）----
VF_10MA = 2.73          # V  グラフ読み取り（参考値）
VF_80MA = 3.10          # V  データシート typ
RD = (VF_80MA - VF_10MA) / (0.080 - 0.010)      # 動的抵抗 [Ω]
V0 = VF_10MA - RD * 0.010                        # 直線の切片 [V]
DVF = 0.30              # V  ユニット間ばらつき（2.8〜3.4 V @80 mA を typ 3.1 V からの ±0.3 V と見なす）
VCC = (3.20, 3.30, 3.40)  # V  仮定
R_SENSE = 1.0           # Ω  電流検出（TP: ILED_x）
R_DS = 0.05             # Ω  仮定
IF_MAX = 0.150          # A  絶対最大定格
PHI_80MA = 26.0         # lm IF=80 mA の全光束 typ
IV_80MA = 8.5           # cd IF=80 mA の光度 typ
I_RATED = 0.080         # A  特性の測定電流（"10% 以上で使うこと" の基準）

TOF_AVG = 0.018         # A  VL53L1X 測距中の平均 max（DS12385 Table 15: typ 16 / max 18 mA）
TOF_PEAK = 0.040        # A  同 ピーク（VCSEL 含む）
N_LED = 2
N_TOF = 2
XSHUT_PU = 3.3 / 10e3   # A  XSHUT を L にしたときのプルアップ電流（1 本あたり）
BUDGET_EXT_3V3 = 0.200  # A  本設計の自己制約: 3V3 から取り出す外部負荷の上限（Seeed 記載 700 mA の約 29%）


def led_current(vcc, dvf, r_led):
    """LED 1 個の電流 [A]。Vf(I) = V0 + dvf + RD*I を代入して解く。"""
    r = r_led + R_SENSE + R_DS + RD
    return max(0.0, (vcc - V0 - dvf) / r)


def report(r_led):
    lo = led_current(min(VCC), +DVF, r_led)     # Vcc 最小 × Vf 最大  → 最小電流
    nom = led_current(3.30, 0.0, r_led)
    hi = led_current(max(VCC), -DVF, r_led)     # Vcc 最大 × Vf 最小  → 最大電流
    return lo, nom, hi


if __name__ == "__main__":
    print(f"Vf モデル: Vf(I) = {V0:.3f} V + {RD:.2f} Ω × I   （10 mA で {VF_10MA} V、80 mA で {VF_80MA} V を通る）")
    print(f"ユニット差 ±{DVF} V、Vcc {min(VCC)}〜{max(VCC)} V、R_sense {R_SENSE} Ω、Rds(on) {R_DS} Ω\n")
    print("R_LED |  I 最小 |  I 公称 |  I 最大 | 最小/80mA | 最大の R 損失 | 2 個の最大 | 判定")
    for r in (10, 15, 20, 22, 27, 33, 47):
        lo, nom, hi = report(r)
        p_r = hi * hi * r
        ok = (lo >= 0.1 * I_RATED) and (hi <= IF_MAX)
        print(f"{r:4d} Ω | {lo*1e3:5.1f} mA | {nom*1e3:5.1f} mA | {hi*1e3:5.1f} mA | "
              f"{lo/I_RATED*100:5.1f} %   | {p_r*1e3:5.1f} mW     | {2*hi*1e3:5.1f} mA | "
              f"{'OK' if ok else 'NG（最小が定格電流の 10% 未満）'}")

    r_led = 20
    lo, nom, hi = report(r_led)
    print(f"\n=== 採用案 R_LED = {r_led} Ω ===")
    print(f"LED 1 個: {lo*1e3:.1f} / {nom*1e3:.1f} / {hi*1e3:.1f} mA（最小/公称/最大）。絶対最大 {IF_MAX*1e3:.0f} mA の {hi/IF_MAX*100:.0f}%")
    for name, i in (("最小", lo), ("公称", nom), ("最大", hi)):
        print(f"  {name}: 光束 ≒ {PHI_80MA*i/I_RATED:.1f} lm、光度 ≒ {IV_80MA*i/I_RATED:.2f} cd"
              f"（IF=80 mA の {i/I_RATED*100:.0f}%。光束が電流に比例と近似 = 概算）")
    led_total = N_LED * hi
    ext_avg = led_total + N_TOF * TOF_AVG + 2 * XSHUT_PU
    ext_peak = led_total + N_TOF * TOF_PEAK + 2 * XSHUT_PU
    print(f"\n3V3 から取る外部負荷（LED は 2 個とも 100% デューティ、最大電流の場合）")
    print(f"  LED {led_total*1e3:.1f} mA + ToF 平均 {N_TOF*TOF_AVG*1e3:.0f} mA + XSHUT プルアップ {2*XSHUT_PU*1e3:.2f} mA = {ext_avg*1e3:.0f} mA")
    print(f"  ToF がピーク（各 {TOF_PEAK*1e3:.0f} mA）のとき {ext_peak*1e3:.0f} mA")
    print(f"  自己制約 {BUDGET_EXT_3V3*1e3:.0f} mA に対して {'収まる' if ext_peak <= BUDGET_EXT_3V3 else '超える'}"
          f"（Seeed 記載の 3V3 出力 700 mA には MCU・カメラ自身の消費も含まれる）")
    print(f"\nGPIO: LED 用は MOSFET のゲートのみ（DC 電流 ≒ 0）。ゲート直列 220 Ω なら充電の瞬間ピークは 3.3/220 = {3.3/220*1e3:.0f} mA。"
          f"XSHUT の L 出力は {XSHUT_PU*1e3:.2f} mA を吸うだけ。")
