#!/usr/bin/env python3
"""NSSW157T の LED 電流（3V3 駆動 / 5V 駆動）と、XIAO の 3V3・5V から取る総電流の計算。

表示するだけのスクリプト（回路図の注記・docs/spec.md の表の元）。標準ライブラリだけで動く。
    python tools/led_budget.py

入力値の出典（README §出典）:
  - Vf(80 mA) typ 3.1 V、Vf の範囲 2.8〜3.4 V (IF=80 mA)、IF max 150 mA（Ta 74 °C まで）、θJA 95 °C/W
    … Nichia STS-DA1-1913 p.1-2, p.9  [原本]
  - Vf(10 mA) ≒ 2.73 V … 同 p.11 の VF-IF グラフの読み取り（"参考値・保証なし" と明記）
  - Vcc: 3V3 = 3.2〜3.4 V、5V(USB) = 4.75〜5.25 V … 仮定（3V3 の精度は Seeed に記載なし。5V は USB 2.0 の規定値）
  - MOSFET の Rds(on) 最大 0.075 Ω @VGS=2.5 V … Si2302CDS（Vishay）。AO3400A は最大 0.048 Ω  [原本]
  - VL53L1X 測距中の平均 16 mA（最大 18）、ピーク 40 mA … ST DS12385 Rev 8 表 15  [原本]
  - Wi-Fi 送信ピーク 340 mA（802.11b 1 Mbps @21 dBm、3.3 V、チップのみ）… Espressif ESP32-S3 Datasheet v2.2 表 5-7  [原本]
  - XIAO ESP32S3 Sense の消費電流（Webcam: 平均 140 mA、撮影ピーク 347 mA @5V / 366 mA @3.8V バッテリー、
    カメラ表の MAX ≒ 0.65 A は測定条件の記載なし）、3V3 出力 700 mA … Seeed wiki  [Wiki]
"""

# ---- LED の Vf モデル: 10 mA と 80 mA の 2 点を通る直線（動作範囲 8〜100 mA では概ね妥当な近似）----
VF_10MA = 2.73          # V  グラフ読み取り（参考値）
VF_80MA = 3.10          # V  データシート typ
RD = (VF_80MA - VF_10MA) / (0.080 - 0.010)      # 動的抵抗 [Ω]
V0 = VF_10MA - RD * 0.010                        # 直線の切片 [V]
DVF = 0.30              # V  ユニット間ばらつき（2.8〜3.4 V @80 mA を typ 3.1 V からの ±0.3 V と見なす）
VCC3 = (3.20, 3.30, 3.40)   # V  仮定
VCC5 = (4.75, 5.00, 5.25)   # V  USB 2.0 の規定値
R_SENSE = 1.0           # Ω  電流検出（TP: ILED_x）
R_DS = 0.075            # Ω  Si2302CDS の最大（@2.5 V）。AO3400A は 0.048 Ω
IF_MAX = 0.150          # A  絶対最大定格（Ta 74 °C まで。p.9）
THETA_JA = 95.0         # °C/W
TJ_MAX = 120.0          # °C
TA_ASSUMED = 50.0       # °C 仮定（基板まわりの周囲温度）
PHI_80MA = 26.0         # lm IF=80 mA の全光束 typ
I_RATED = 0.080         # A  特性の測定電流（"10% 以上で使うこと" の基準と解釈）

# ---- 電源まわり ----
TOF_AVG, TOF_PEAK = 0.018, 0.040     # A  VL53L1X（1 個あたり）
N_LED, N_TOF = 2, 2
XSHUT_PU = 3.3 / 10e3                # A  XSHUT を L にしたときのプルアップ電流（1 本）
SEEED_3V3_MAX = 0.700                # A  Seeed wiki "You can draw 700mA"（条件の記載なし）
XIAO_WEBCAM_AVG = 0.140              # A  Seeed wiki（5V）
XIAO_WEBCAM_PEAK_5V = 0.347          # A  Seeed wiki（5V、撮影ピーク）
XIAO_WEBCAM_PEAK_BAT = 0.366         # A  Seeed wiki（3.8V バッテリー、撮影ピーク）
XIAO_CAM_TABLE_MAX = 0.650           # A  Seeed wiki カメラ比較表の OV2640 MAX（測定条件の記載なし = 未確認）
ESP32S3_WIFI_TX_PEAK = 0.340         # A  Espressif DS 表 5-7（チップのみ。カメラ・PSRAM・Flash は含まない）
USB2_LIMIT = 0.500                   # A  USB 2.0 の既定（高出力ポートなら 900 mA 以上のこともある = 未確認）
E24 = [10, 11, 12, 13, 15, 16, 18, 20, 22, 24, 27, 30, 33, 36, 39, 43, 47, 51, 56, 62, 68, 75, 82, 91, 100]
PKG = {"0603": 0.100, "0805": 0.125, "1206": 0.250, "2010": 0.500, "2512": 1.000}   # 定格電力 [W]（一般的な厚膜）


def led_current(vcc, dvf, r_ser):
    """LED 1 個の電流 [A]。Vf(I) = V0 + dvf + RD*I。r_ser = 直列抵抗の合計（R_LED + R_SENSE + Rds(on)）。"""
    return max(0.0, (vcc - V0 - dvf) / (r_ser + RD))


def stats(vcc_set, r_led):
    r = r_led + R_SENSE + R_DS
    lo = led_current(min(vcc_set), +DVF, r)       # Vcc 最小 × Vf 高 → 最小電流
    nom = led_current(vcc_set[1], 0.0, r)
    hi = led_current(max(vcc_set), -DVF, r)       # Vcc 最大 × Vf 低 → 最大電流
    return lo, nom, hi


def tj(i_hi):
    vf = V0 - DVF + RD * i_hi
    return TA_ASSUMED + THETA_JA * i_hi * vf


def section(title):
    print(f"\n{'=' * 6} {title} {'=' * 6}")


if __name__ == "__main__":
    print(f"Vf モデル: Vf(I) = {V0:.3f} V + {RD:.2f} Ω × I   （10 mA で {VF_10MA} V、80 mA で {VF_80MA} V を通る）")
    print(f"ユニット差 ±{DVF} V、R_sense {R_SENSE} Ω、Rds(on) {R_DS} Ω（Si2302CDS 最大。AO3400A は 0.048 Ω で差は 1 mV 以下）")

    # ---------------- 3V3 駆動 ----------------
    section(f"3V3 駆動（Vcc {min(VCC3)}〜{max(VCC3)} V）: R_LED の選び方")
    print("R_LED |  I 最小 |  I 公称 |  I 最大 | 最小/80mA | R の最大損失 | 判定（最小 ≧ 8 mA = 80 mA の 10%）")
    for r in (10, 15, 20, 22, 27, 33):
        lo, nom, hi = stats(VCC3, r)
        print(f"{r:4d} Ω | {lo*1e3:5.1f} mA | {nom*1e3:5.1f} mA | {hi*1e3:5.1f} mA | {lo/I_RATED*100:5.1f} %   | "
              f"{hi*hi*r*1e3:5.1f} mW   | {'OK' if lo >= 0.1 * I_RATED else 'NG'}")
    lo3, nom3, hi3 = stats(VCC3, 20)
    print(f"採用: 20 Ω 0603（0.1 W）。最大 {hi3*1e3:.1f} mA → R の損失 {hi3*hi3*20*1e3:.0f} mW = 定格の {hi3*hi3*20/0.1*100:.0f}%")
    print(f"  LED 1 個 {lo3*1e3:.1f} / {nom3*1e3:.1f} / {hi3*1e3:.1f} mA（最小/公称/最大）。光束 ≒ "
          f"{PHI_80MA*lo3/I_RATED:.1f} / {PHI_80MA*nom3/I_RATED:.1f} / {PHI_80MA*hi3/I_RATED:.1f} lm（80 mA の {lo3/I_RATED*100:.0f}/{nom3/I_RATED*100:.0f}/{hi3/I_RATED*100:.0f}%）")

    # ---------------- 5V 駆動 ----------------
    section(f"5V 駆動（Vcc {min(VCC5)}〜{max(VCC5)} V）: 抵抗の値とサイズ")
    print("選定基準: ① 最悪時の抵抗損失 ≦ 定格の 50%（ディレーティング）② 最大電流 ≦ 100 mA（絶対最大 150 mA の 2/3）"
          f" ③ 最小電流 ≧ 8 mA ④ Tj(Ta={TA_ASSUMED:.0f}°C) ≦ {TJ_MAX:.0f}°C"
          f" ⑤ 5V の合計（LED 2 個の最大 + XIAO の撮影ピーク {XIAO_WEBCAM_PEAK_5V*1e3:.0f} mA）≦ USB 2.0 の 500 mA")
    print("サイズ | R      |  I 最小 |  I 公称 |  I 最大 | R の最大損失 (定格比) | Tj      | 80 mA 比(公称) | 判定")
    chosen = {}
    for pk in ("0603", "0805", "1206", "2010", "2512"):
        for r in E24:
            lo, nom, hi = stats(VCC5, r)
            p = hi * hi * r
            ok = (p <= 0.5 * PKG[pk]) and hi <= 0.100 and lo >= 0.1 * I_RATED and tj(hi) <= TJ_MAX                 and (N_LED * hi + XIAO_WEBCAM_PEAK_5V <= USB2_LIMIT)
            if ok and pk not in chosen:
                chosen[pk] = r            # 各サイズで「基準を満たす最小の E24 値」= 最も明るい
        if pk in chosen:
            r = chosen[pk]
            lo, nom, hi = stats(VCC5, r)
            p = hi * hi * r
            print(f"{pk:5s} | {r:3d} Ω | {lo*1e3:5.1f} mA | {nom*1e3:5.1f} mA | {hi*1e3:5.1f} mA | "
                  f"{p*1e3:6.1f} mW ({p/PKG[pk]*100:3.0f}%)        | {tj(hi):5.1f}°C | {nom/I_RATED*100:5.0f} %        | 基準を満たす最小値")
        else:
            print(f"{pk:5s} | （基準を満たす値なし）")
    r_alt = chosen["2010"]
    print(f"\n参考: 1206 のまま R = {r_alt} Ω にすると")
    lo, nom, hi = stats(VCC5, r_alt)
    print(f"  I {lo*1e3:.0f}/{nom*1e3:.0f}/{hi*1e3:.0f} mA、R の最大損失 {hi*hi*r_alt*1e3:.0f} mW = 1206 定格（250 mW）の {hi*hi*r_alt/0.25*100:.0f}% → 基準 ①を満たさない")
    lo, nom, hi = stats(VCC5, 24)
    print(f"参考: 2010 で R = 24 Ω（USB の条件を外すと最も明るい値）: I {lo*1e3:.0f}/{nom*1e3:.0f}/{hi*1e3:.0f} mA、"
          f"5V の合計 {(N_LED*hi+XIAO_WEBCAM_PEAK_5V)*1e3:.0f} mA → 基準 ⑤ を満たさない")
    r5 = chosen["2010"]
    lo5, nom5, hi5 = stats(VCC5, r5)
    print(f"\n採用: {r5} Ω 2010（0.5 W）。LED 1 個 {lo5*1e3:.1f} / {nom5*1e3:.1f} / {hi5*1e3:.1f} mA、"
          f"光束 ≒ {PHI_80MA*nom5/I_RATED:.1f} lm（80 mA の {nom5/I_RATED*100:.0f}%）、最大 {hi5*1e3:.0f} mA は絶対最大の {hi5/IF_MAX*100:.0f}%")
    print(f"  LED の損失 最大 {hi5*(V0-DVF+RD*hi5)*1e3:.0f} mW（定格 510 mW）、Tj = {tj(hi5):.0f}°C（Ta {TA_ASSUMED:.0f}°C、上限 {TJ_MAX:.0f}°C）")
    wrong = stats(VCC5, 20)
    print(f"  ※ 5V なのに 3V3 用の 20 Ω を使うと最大 {wrong[2]*1e3:.0f} mA（0603 の損失 {wrong[2]**2*20*1e3:.0f} mW = 定格の {wrong[2]**2*20/0.1*100:.0f}%）")

    # ---------------- 3V3 総電流 ----------------
    section("3V3 から取る電流の合計（Wi-Fi・カメラのピークを含む）")
    led3 = N_LED * hi3
    tof_avg, tof_pk = N_TOF * TOF_AVG, N_TOF * TOF_PEAK
    ext_3v3_led3v3 = led3 + tof_pk + 2 * XSHUT_PU           # LED を 3V3 で駆動（既定）
    ext_3v3_led5v = tof_pk + 2 * XSHUT_PU                   # LED を 5V で駆動（半田ジャンパー）
    print(f"基板側（外部負荷）: LED(3V3, 最大) {led3*1e3:.1f} + ToF ピーク {tof_pk*1e3:.0f} + XSHUT プルアップ {2*XSHUT_PU*1e3:.1f}"
          f" = {ext_3v3_led3v3*1e3:.0f} mA（LED を 5V にすると {ext_3v3_led5v*1e3:.0f} mA）")
    print(f"XIAO 側（自身の消費）: 下の 3 通り。3V3 が LDO なら 3V3 側の電流 ≒ 入力側の電流"
          f"（Seeed の撮影ピークは 5V で {XIAO_WEBCAM_PEAK_5V*1e3:.0f} mA、3.8V バッテリーで {XIAO_WEBCAM_PEAK_BAT*1e3:.0f} mA とほぼ同じ → 電圧に依らない = LDO 的。"
          f"レギュレータの型番は Seeed に記載なし = 未確認）")
    print("\n想定 (XIAO 自身)                                   | XIAO 分 | LED=3V3 の合計 (700 mA 比) | LED=5V の合計 (700 mA 比) | 出典・確認")
    rows = [
        ("A. Webcam 平均（Wi-Fi 配信 + カメラ）", XIAO_WEBCAM_AVG, "Seeed wiki（平均）"),
        ("B. Webcam 撮影ピーク（3.8V バッテリー側の値）", XIAO_WEBCAM_PEAK_BAT, "Seeed wiki（ピーク）"),
        ("C. カメラ比較表の MAX（OV2640 ≒ 0.65 A）", XIAO_CAM_TABLE_MAX, "Seeed wiki。**測定条件の記載なし = 未確認**"),
        ("D. Wi-Fi 送信ピークのチップ単体 340 mA（参考）", ESP32S3_WIFI_TX_PEAK, "Espressif DS v2.2 表 5-7（カメラ等は含まない）"),
    ]
    for name, x, src in rows:
        t1, t2 = x + ext_3v3_led3v3, x + ext_3v3_led5v
        print(f"{name:48s} | {x*1e3:4.0f} mA | {t1*1e3:4.0f} mA ({t1/SEEED_3V3_MAX*100:3.0f}%)            | {t2*1e3:4.0f} mA ({t2/SEEED_3V3_MAX*100:3.0f}%)            | {src}")
    print(f"\n判定: B（撮影ピーク）までなら {((XIAO_WEBCAM_PEAK_BAT+ext_3v3_led3v3)*1e3):.0f} mA で 700 mA 以内。"
          f"C を上限と見ると {((XIAO_CAM_TABLE_MAX+ext_3v3_led3v3)*1e3):.0f} mA で超過（LED を 5V にしても {((XIAO_CAM_TABLE_MAX+ext_3v3_led5v)*1e3):.0f} mA で 700 mA 付近）。"
          "C の条件は未確認 → 実機で 5V 入力電流を測るまで、Wi-Fi 送信・撮影・LED 100%・ToF ピークを同時にしない運用が安全側。")

    # ---------------- 5V 側 ----------------
    section("5V ピン（USB VBUS）から取る電流（LED を 5V にした場合）")
    led5 = N_LED * hi5
    print(f"LED 2 個 最大 {led5*1e3:.0f} mA（公称 {N_LED*nom5*1e3:.0f} mA）。XIAO 自身の入力側の電流が別に流れる（B: {XIAO_WEBCAM_PEAK_5V*1e3:.0f} mA @5V）")
    print(f"  合計 最大 {(led5+XIAO_WEBCAM_PEAK_5V)*1e3:.0f} mA（USB 2.0 の既定 500 mA を {'超える' if led5+XIAO_WEBCAM_PEAK_5V > 0.5 else '超えない'}）。"
          "XIAO の 5V ピンの電流能力は Seeed に記載なし = 未確認。")

    # ---------------- GPIO ----------------
    section("GPIO")
    print("LED 用は MOSFET のゲートのみ（DC 電流 ≒ 0）。ゲート直列 220 Ω なら充電の瞬間ピークは 3.3/220 = "
          f"{3.3/220*1e3:.0f} mA。XIAO の GPIO は IOH 40 mA / IOL 28 mA（ESP32-S3 DS v2.2 表 5-4、PAD_DRIVER=3）、"
          f"XSHUT の L 出力は {XSHUT_PU*1e3:.2f} mA を吸うだけ。VOH 最小 0.8×VDD = 2.64 V なので、ゲート駆動電圧は最悪でも 2.64 V"
          "（MOSFET の Rds(on) 規定 VGS=2.5 V 以上）。")
