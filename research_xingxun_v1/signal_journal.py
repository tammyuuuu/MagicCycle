# -*- coding: utf-8 -*-
"""信号版本管理：按日期冻结，不允许覆盖历史。

规则：
- 每天最多一份信号快照：signals/YYYY-MM-DD.csv
- 同一天重复发布相同内容 → 视为无变化；
- 同一天重复发布不同内容 → 拒绝（必须新增版本文件或修订说明）；
- 任何历史文件都不删除、不修改。
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
SIGNAL_DIR = ROOT / "signals"
SIGNAL_DIR.mkdir(exist_ok=True)


def publish(rows, date, note=""):
    df = pd.DataFrame(rows).sort_values("code").reset_index(drop=True)
    path = SIGNAL_DIR / f"{date}.csv"
    if path.exists():
        old = pd.read_csv(path, dtype={"code": str})
        new = df.copy()
        new["code"] = new["code"].astype(str)
        if old.shape == new.shape and list(old.columns) == list(new.columns):
            same = all(old[c].astype(str).tolist() == new[c].astype(str).tolist()
                       for c in old.columns)
            if same:
                return dict(status="unchanged", path=str(path))
        raise FileExistsError(
            f"{path.name} 已存在且内容不同：历史信号不可覆盖。"
            "如需修订，请新增版本号（例如 {date}_v2.csv）并在报告中说明原因。")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    if note:
        (SIGNAL_DIR / f"{date}.note.txt").write_text(note, encoding="utf-8")
    return dict(status="created", path=str(path))


def list_signals():
    return sorted(p.stem for p in SIGNAL_DIR.glob("*.csv"))


def load(date):
    return pd.read_csv(SIGNAL_DIR / f"{date}.csv", dtype={"code": str})


if __name__ == "__main__":
    print("signals:", list_signals())
