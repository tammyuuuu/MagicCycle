# -*- coding: utf-8 -*-
"""V2.3 补充：逆波动权重披露、分段稳定性、限购替代公平比较。"""
import numpy as np
import pandas as pd

from run_v23 import CASH, load_all, month_ret, invvol_w, run

panel = load_all()
rets = month_ret(panel)
segs = [("2021-11~2023-12", "2021-11-01", "2023-12-31"),
        ("2024-01~2026-10", "2024-01-01", "2026-10-21"),
        ("全样本", "2021-11-01", "2026-10-21")]

schemes = {
    "逆波动 Core3": (lambda h, dt: invvol_w(h, ["000015", "008701", "161130"], 120, 0.6), ["000015", "008701", "161130"]),
    "逆波动 Core4": (lambda h, dt: invvol_w(h, ["000015", "008701", "161130", "050025"], 120, 0.6), ["000015", "008701", "161130", "050025"]),
    "固定 Core3": (lambda h, dt: {"000015": 1/3, "008701": 1/3, "161130": 1/3}, ["000015", "008701", "161130"]),
    "固定 Core4": (lambda h, dt: {"000015": .25, "008701": .25, "161130": .25, "050025": .25}, ["000015", "008701", "161130", "050025"]),
    "债/金 50/50": (lambda h, dt: {"000015": .5, "008701": .5}, ["000015", "008701"]),
    "逆波动 债/金": (lambda h, dt: invvol_w(h, ["000015", "008701"], 120, 0.8), ["000015", "008701"]),
    "债/金/500 各1/3": (lambda h, dt: {"000015": 1/3, "008701": 1/3, "160119": 1/3}, ["000015", "008701", "160119"]),
    "逆波动 债/金/500": (lambda h, dt: invvol_w(h, ["000015", "008701", "160119"], 120, 0.6), ["000015", "008701", "160119"]),
    "债/金/创业板 各1/3": (lambda h, dt: {"000015": 1/3, "008701": 1/3, "110026": 1/3}, ["000015", "008701", "110026"]),
    "债/金/300 各1/3": (lambda h, dt: {"000015": 1/3, "008701": 1/3, "160706": 1/3}, ["000015", "008701", "160706"]),
    "债/金/红利 各1/3": (lambda h, dt: {"000015": 1/3, "008701": 1/3, "090010": 1/3}, ["000015", "008701", "090010"]),
    "债/金/科创 各1/3": (lambda h, dt: {"000015": 1/3, "008701": 1/3, "011612": 1/3}, ["000015", "008701", "011612"]),
}

print("== 分段收益/回撤 ==")
rows = []
for name, (wf, codes) in schemes.items():
    for seg, s, e in segs:
        m, pack = run(panel, rets, wf, s, e)
        if not m:
            continue
        avg_w = {c: np.mean([r[2].get(c, 0) for r in pack[2]]) for c in codes}
        rows.append(dict(scheme=name, seg=seg, cagr=m["cagr"], mdd=m["mdd"],
                         calmar=m["calmar"], **{f"w_{c}": avg_w[c] for c in codes}))
df = pd.DataFrame(rows)
print(df.round(4).to_string(index=False))

print("\n== 逆波动平均权重（全样本） ==")
for name in ["逆波动 Core3", "逆波动 Core4", "逆波动 债/金", "逆波动 债/金/500"]:
    wf, codes = schemes[name]
    m, pack = run(panel, rets, wf, "2021-11-01", "2026-10-21")
    last = pack[2][-1][2]
    print(name, "平均", {k: round(v, 3) for k, v in
                         {c: np.mean([r[2].get(c, 0) for r in pack[2]]) for c in codes}.items()},
          "最近", {k: round(v, 3) for k, v in last.items()})
