#!/usr/bin/env python3
"""liki-divination snapshot / ask 工具的 CLI 适配器。"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from functools import lru_cache
from pathlib import Path

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError as exc:
    raise ImportError(
        "liki-divination tools require jsonschema; "
        "install with `python3 -m pip install -r tools/requirements.txt`"
    ) from exc

from huangli_days import days as huangli_days
from liuyao_ask import ask as liuyao_ask
from liuyao_snapshot import create as liuyao_snapshot
from qimen_ask import ask as qimen_ask
from qimen_snapshot import create as qimen_snapshot
from divination_rpc import ensure_engine_compatible


_TOOLFACE_PATH = Path(__file__).with_name("skill-tools.json")


@lru_cache
def _toolface_schemas() -> dict[str, dict]:
    document = json.loads(_TOOLFACE_PATH.read_text(encoding="utf-8"))
    return {
        item["function"]["name"]: item["function"]["parameters"]
        for item in document["tools"]
    }


def _validate_tool_args(fn: str, args: dict) -> None:
    schema = _toolface_schemas().get(fn)
    if schema is None:
        raise ValueError(f"unknown tool: {fn}")
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(args),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
            for error in errors
        )
        raise ValueError(f"invalid {fn} args: {details}")


def _configure_windows_stdio() -> None:
    if os.name != "nt":
        return
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    except (AttributeError, OSError):
        pass


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def _run_bazi_probe_to_stderr() -> None:
    """Temporary branch-only probe: execute the local Liki engine's real bazi.chart/bazi.bond RPCs.

    All three charts use the same placeholder 12:00 Beijing clock time. The consumer will
    discard every hour-pillar-derived relationship when comparing the two pairs.
    """
    url = os.environ.get("LIKI_RPC_URL")
    if not url:
        return

    def rpc(method: str, params: dict):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if payload.get("error"):
            raise RuntimeError(f"{method}: {payload['error']}")
        return payload["result"]["data"]

    f2002 = rpc("bazi.chart", {"solar_time": "2002-06-17T12:00:00+08:00", "gender": "female"})
    male = rpc("bazi.chart", {"solar_time": "2003-03-20T12:00:00+08:00", "gender": "male"})
    f2005 = rpc("bazi.chart", {"solar_time": "2005-07-31T12:00:00+08:00", "gender": "female"})
    bond_a = rpc("bazi.bond", {"a": {"chart": f2002}, "b": {"chart": male}})
    bond_b = rpc("bazi.bond", {"a": {"chart": f2005}, "b": {"chart": male}})
    result = {
        "female_2002_chart": f2002,
        "male_2003_chart": male,
        "female_2005_chart": f2005,
        "pair_2002_2003": bond_a,
        "pair_2005_2003": bond_b,
    }
    print("CHATGPT_BAZI_BOND_RESULT=" + json.dumps(result, ensure_ascii=False, sort_keys=True), file=sys.stderr)


_DISPATCH = {
    "liuyao_snapshot": lambda args: liuyao_snapshot(
        question=args["question"],
        mode=args.get("mode", "auto"),
        rounds=args.get("rounds"),
        yaos=args.get("yaos"),
        matter=args.get("matter"),
        yong_shen=args.get("yong_shen"),
        perspective=args.get("perspective"),
        topic=args.get("topic"),
    ),
    "liuyao_ask": lambda args: liuyao_ask(
        args["snapshot"],
        message=args["message"],
    ),
    "qimen_snapshot": lambda args: qimen_snapshot(
        question=args["question"],
        city=args.get("city"),
        longitude=args.get("longitude"),
        time=args.get("time"),
        matter=args.get("matter"),
        yong_shen=args.get("yong_shen"),
        rule=args.get("rule"),
        scope=args.get("scope"),
        school=args.get("school"),
        dingju_method=args.get("dingju_method"),
        quarter_rule=args.get("quarter_rule"),
        base_dingju_method=args.get("base_dingju_method"),
        dun_source=args.get("dun_source"),
        hour_boundary=args.get("hour_boundary"),
        birth_date=args.get("birth_date"),
    ),
    "qimen_ask": lambda args: qimen_ask(
        args["snapshot"],
        message=args["message"],
    ),
    "huangli_days": lambda args: huangli_days(
        question=args["question"],
        event=args.get("event"),
        start_date=args.get("start_date"),
        end_date=args.get("end_date"),
        days=args.get("days"),
    ),
}


def _dispatch(fn: str, args: dict):
    _validate_tool_args(fn, args)
    handler = _DISPATCH.get(fn)
    if handler is None:
        raise ValueError(f"unknown tool: {fn}")
    return handler(args)


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        _emit({"ok": False, "error": "empty stdin"})
        return 0
    try:
        ensure_engine_compatible()
        request = json.loads(raw)
        args = request.get("args", {})
        if not isinstance(args, dict):
            raise ValueError("args must be an object")
        if request.get("fn") == "liuyao_snapshot":
            _run_bazi_probe_to_stderr()
        _emit({"ok": True, "data": _dispatch(request["fn"], args)})
    except KeyError as error:
        _emit({"ok": False, "error": f"missing arg: {error}"})
    except Exception as error:  # noqa: BLE001 — 工具链错误统一转为 JSON error
        _emit({"ok": False, "error": f"{type(error).__name__}: {error}"})
    return 0


if __name__ == "__main__":
    _configure_windows_stdio()
    sys.exit(main())
