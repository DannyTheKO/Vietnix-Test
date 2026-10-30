"""Command-line entry point: python -m pve_balance ..."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .loader import DataError, load_dataset
from .metrics import compute_loads, evaluate_all
from .models import Thresholds
from .planner import plan_migrations
from .report import render_text, to_json

# Default path points at the data file shipped with the tool.
DEFAULT_INPUT = Path(__file__).resolve().parent.parent / "data" / "cluster-pve-hcm-c3.json"


def _force_utf8_stdout() -> None:
    """The Windows console may default to cp1252 and break non-ASCII output."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except ValueError:
                pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pve-balance",
        description="Read a Proxmox VE cluster snapshot, compute load and propose migrations.",
    )
    parser.add_argument(
        "-i",
        "--input",
        default=str(DEFAULT_INPUT),
        help=f"input JSON snapshot (default: {DEFAULT_INPUT.name})",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=("table", "json"),
        default="table",
        help="output format (default: table)",
    )
    parser.add_argument(
        "--cpu-threshold",
        type=float,
        default=80.0,
        help="CPU %% considered overloaded (default: 80)",
    )
    parser.add_argument(
        "--mem-threshold",
        type=float,
        default=85.0,
        help="RAM %% considered overloaded (default: 85)",
    )
    parser.add_argument(
        "--overcommit-threshold",
        type=float,
        default=2.0,
        help="vCPU overcommit threshold (default: 2.0)",
    )
    parser.add_argument(
        "--fail-on-overload",
        action="store_true",
        help="exit code 1 when any node is overloaded (for cron/CI)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print data warnings to stderr",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)

    if not 0 < args.cpu_threshold <= 100:
        parser.error("--cpu-threshold must be in (0, 100]")
    if not 0 < args.mem_threshold <= 100:
        parser.error("--mem-threshold must be in (0, 100]")
    if args.overcommit_threshold <= 0:
        parser.error("--overcommit-threshold must be > 0")

    thresholds = Thresholds(
        cpu_pct=args.cpu_threshold,
        mem_pct=args.mem_threshold,
        overcommit=args.overcommit_threshold,
    )

    try:
        dataset = load_dataset(args.input)
    except DataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    loads = compute_loads(dataset.nodes, dataset.vms)
    evaluations = evaluate_all(loads, thresholds)
    plan = plan_migrations(loads, dataset.vms, thresholds)

    if args.format == "json":
        print(to_json(dataset, evaluations, plan, thresholds))
    else:
        print(render_text(dataset, evaluations, plan, thresholds))

    if args.verbose:
        for warning in dataset.warnings:
            print(f"warn: {warning}", file=sys.stderr)

    if args.fail_on_overload and any(e.overloaded for e in evaluations.values()):
        return 1
    return 0
