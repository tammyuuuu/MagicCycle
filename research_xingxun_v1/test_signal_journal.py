# -*- coding: utf-8 -*-
"""信号冻结与版本管理测试。运行：python test_signal_journal.py"""
from pathlib import Path
import shutil
import tempfile

import signal_journal as sj


def rows(val=1.0):
    return [dict(date="2026-10-22", code="000216", strategy="A_hold",
                 strategy_version="hold_v1", target_position=val),
            dict(date="2026-10-22", code="160706", strategy="A_hold",
                 strategy_version="hold_v1", target_position=1.0)]


def test_create_then_unchanged():
    tmp = Path(tempfile.mkdtemp())
    old = sj.SIGNAL_DIR
    sj.SIGNAL_DIR = tmp
    try:
        a = sj.publish(rows(), "2026-10-22")
        assert a["status"] == "created"
        b = sj.publish(rows(), "2026-10-22")
        assert b["status"] == "unchanged"
    finally:
        sj.SIGNAL_DIR = old
        shutil.rmtree(tmp)


def test_refuse_overwrite_with_different_content():
    tmp = Path(tempfile.mkdtemp())
    old = sj.SIGNAL_DIR
    sj.SIGNAL_DIR = tmp
    try:
        sj.publish(rows(), "2026-10-22")
        try:
            sj.publish(rows(0.5), "2026-10-22")
            raise AssertionError("应当拒绝覆盖")
        except FileExistsError:
            pass
    finally:
        sj.SIGNAL_DIR = old
        shutil.rmtree(tmp)


def test_list_and_load():
    tmp = Path(tempfile.mkdtemp())
    old = sj.SIGNAL_DIR
    sj.SIGNAL_DIR = tmp
    try:
        sj.publish(rows(), "2026-10-22")
        assert sj.list_signals() == ["2026-10-22"]
        d = sj.load("2026-10-22")
        assert len(d) == 2 and str(d["code"].iloc[0]) == "000216"
    finally:
        sj.SIGNAL_DIR = old
        shutil.rmtree(tmp)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("signal journal tests passed")
