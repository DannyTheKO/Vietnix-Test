"""Render results: a table for humans and JSON for machines."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Iterable, Sequence

from . import __version__
from .loader import Dataset
from .models import NodeEvaluation, Thresholds
from .planner import Migration, Plan, Snapshot

BAR_WIDTH = 8


def human_bytes(value: int | None) -> str:
    if value is None:
        return "n/a"
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    number = float(value)
    unit = units[0]
    for unit in units:
        if number < 1024 or unit == units[-1]:
            break
        number /= 1024
    return f"{number:.1f} {unit}"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}%"


def _bar(value: float | None) -> str:
    if value is None:
        return "-" * BAR_WIDTH
    filled = round(max(0.0, min(100.0, value)) / 100 * BAR_WIDTH)
    return "#" * filled + "-" * (BAR_WIDTH - filled)


def _cell_align(text: str, width: int, align: str) -> str:
    if align == "r":
        return text.rjust(width)
    if align == "c":
        return text.center(width)
    return text.ljust(width)


def render_table(
    headers: Sequence[str],
    rows: Iterable[Sequence[str]],
    aligns: Sequence[str] | None = None,
) -> list[str]:
    """Simple ASCII table, no external dependencies."""
    rows = [list(map(str, row)) for row in rows]
    aligns = list(aligns or ["l"] * len(headers))
    widths = []
    for index, header in enumerate(headers):
        cells = [len(str(row[index])) for row in rows]
        widths.append(max([len(str(header))] + cells))

    separator = "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    def line(values: Sequence[str], use_aligns: Sequence[str]) -> str:
        parts = [
            " " + _cell_align(str(value), widths[i], use_aligns[i]) + " "
            for i, value in enumerate(values)
        ]
        return "|" + "|".join(parts) + "|"

    output = [separator, line(headers, ["c"] * len(headers)), separator]
    output.extend(line(row, aligns) for row in rows)
    output.append(separator)
    return output


def _node_flag(evaluation: NodeEvaluation, thresholds: Thresholds) -> str:
    load = evaluation.load
    if not load.node.is_online:
        return "off"
    if evaluation.overloaded:
        return "OVER"
    risky = (
        (load.overcommit is not None and load.overcommit >= thresholds.overcommit)
        or load.mem_pct is None
        or load.unknown_mem_vms > 0
    )
    return "risk" if risky else "ok"


def _snapshot_text(snapshot: Snapshot) -> str:
    overcommit = "n/a" if snapshot.overcommit is None else f"{snapshot.overcommit:.2f}"
    return (
        f"CPU {_pct(snapshot.cpu_pct)} | "
        f"RAM {_pct(snapshot.mem_pct)} | "
        f"OC {overcommit}"
    )


def _migration_lines(migration: Migration, step: int) -> list[str]:
    vm = migration.vm
    return [
        f"  #{step} vmid {vm.vmid} ({vm.name}): "
        f"{migration.source} -> {migration.target} "
        f"[{vm.vcpus} vCPU, {human_bytes(vm.mem_used)}]",
        f"     {migration.source}: {_snapshot_text(migration.source_before)}"
        f"  =>  {_snapshot_text(migration.source_after)}",
        f"     {migration.target}: {_snapshot_text(migration.target_before)}"
        f"  =>  {_snapshot_text(migration.target_after)}",
    ]


def render_text(
    dataset: Dataset,
    evaluations: dict[str, NodeEvaluation],
    plan: Plan,
    thresholds: Thresholds,
) -> str:
    lines: list[str] = []
    lines.append("Proxmox VE cluster load report")
    lines.append(f"Cluster  : {dataset.cluster}")
    lines.append(f"Snapshot : {dataset.collected_at or 'unknown'}")
    lines.append(
        f"Thresholds: CPU >= {thresholds.cpu_pct:.1f}% | "
        f"RAM >= {thresholds.mem_pct:.1f}% | "
        f"vCPU overcommit >= {thresholds.overcommit:.2f}"
    )
    lines.append("")

    headers = ["Node", "Status", "Cores", "vCPU", "OC", "CPU", "RAM", "Flag"]
    rows: list[list[str]] = []
    for evaluation in evaluations.values():
        load = evaluation.load
        rows.append(
            [
                load.node.name,
                load.node.status,
                str(load.node.cpu_cores) if load.node.cpu_cores is not None else "n/a",
                str(load.vcpus_running),
                f"{load.overcommit:.2f}" if load.overcommit is not None else "n/a",
                f"{_pct(load.cpu_pct)} {_bar(load.cpu_pct)}",
                f"{_pct(load.mem_pct)} {_bar(load.mem_pct)}",
                _node_flag(evaluation, thresholds),
            ]
        )
    lines.extend(
        render_table(headers, rows, aligns=["l", "l", "r", "r", "r", "l", "l", "c"])
    )
    lines.append("")

    lines.append("OVERLOADED NODES")
    overloaded = [evaluation for evaluation in evaluations.values() if evaluation.overloaded]
    if overloaded:
        for evaluation in overloaded:
            lines.append(f"  {evaluation.name}: " + "; ".join(evaluation.reasons))
    else:
        lines.append("  none")
    lines.append("")

    lines.append("MIGRATION PLAN (greedy, dry-run)")
    if plan.migrations:
        for step, migration in enumerate(plan.migrations, start=1):
            lines.extend(_migration_lines(migration, step))
    else:
        lines.append("  none")
    lines.append("")

    if plan.unresolved:
        lines.append("STILL OVERLOADED AFTER PLAN")
        for name in plan.unresolved:
            lines.append(f"  {name}")
        lines.append("")

    if plan.notes:
        lines.append("PLANNER NOTES")
        for note in plan.notes:
            lines.append(f"  - {note}")
        lines.append("")

    lines.append(f"DATA WARNINGS ({len(dataset.warnings)})")
    if dataset.warnings:
        for warning in dataset.warnings:
            lines.append(f"  - {warning}")
    else:
        lines.append("  none")

    return "\n".join(lines)


def _snapshot_dict(snapshot: Snapshot) -> dict:
    return {
        "cpu_usage_pct": None if snapshot.cpu_pct is None else round(snapshot.cpu_pct, 2),
        "mem_usage_pct": None if snapshot.mem_pct is None else round(snapshot.mem_pct, 2),
        "vcpu_overcommit": None
        if snapshot.overcommit is None
        else round(snapshot.overcommit, 2),
        "vcpus_allocated": snapshot.vcpus,
        "mem_used_bytes": snapshot.mem_used_bytes,
    }


def _migration_dict(migration: Migration, step: int) -> dict:
    vm = migration.vm
    return {
        "step": step,
        "vmid": vm.vmid,
        "vm_name": vm.name,
        "vcpus": vm.vcpus,
        "mem_used_bytes": vm.mem_used,
        "from": migration.source,
        "to": migration.target,
        "source_before": _snapshot_dict(migration.source_before),
        "source_after": _snapshot_dict(migration.source_after),
        "target_before": _snapshot_dict(migration.target_before),
        "target_after": _snapshot_dict(migration.target_after),
    }


def to_json_dict(
    dataset: Dataset,
    evaluations: dict[str, NodeEvaluation],
    plan: Plan,
    thresholds: Thresholds,
) -> dict:
    nodes = []
    for evaluation in evaluations.values():
        load = evaluation.load
        nodes.append(
            {
                "node": load.node.name,
                "status": load.node.status,
                "cpu_cores": load.node.cpu_cores,
                "mem_total_bytes": load.node.mem_total,
                "running_vms": load.running_vms,
                "stopped_vms": load.stopped_vms,
                "vcpus_allocated": load.vcpus_running,
                "vcpus_stopped": load.vcpus_stopped,
                "cpu_used_cores": round(load.cpu_used_cores, 2),
                "cpu_usage_pct": None if load.cpu_pct is None else round(load.cpu_pct, 2),
                "vcpu_overcommit": None
                if load.overcommit is None
                else round(load.overcommit, 2),
                "mem_used_bytes": load.mem_used_bytes,
                "mem_usage_pct": None if load.mem_pct is None else round(load.mem_pct, 2),
                "overloaded": evaluation.overloaded,
                "overload_reasons": evaluation.reasons,
                "warnings": evaluation.warnings,
            }
        )

    return {
        "tool": "pve-balance",
        "version": __version__,
        "cluster": dataset.cluster,
        "collected_at": dataset.collected_at,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "thresholds": {
            "cpu_pct": thresholds.cpu_pct,
            "mem_pct": thresholds.mem_pct,
            "vcpu_overcommit": thresholds.overcommit,
        },
        "nodes": nodes,
        "overloaded_nodes": [e.name for e in evaluations.values() if e.overloaded],
        "migrations": [
            _migration_dict(migration, step)
            for step, migration in enumerate(plan.migrations, start=1)
        ],
        "unresolved_nodes": plan.unresolved,
        "planner_notes": plan.notes,
        "data_warnings": dataset.warnings,
    }


def to_json(
    dataset: Dataset,
    evaluations: dict[str, NodeEvaluation],
    plan: Plan,
    thresholds: Thresholds,
) -> str:
    return json.dumps(
        to_json_dict(dataset, evaluations, plan, thresholds),
        ensure_ascii=False,
        indent=2,
    )
