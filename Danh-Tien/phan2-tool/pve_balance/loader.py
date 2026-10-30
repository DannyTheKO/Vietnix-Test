"""Read and validate the JSON snapshot.

Rules:
- Structural errors (missing file, broken JSON, missing `nodes`/`vms` arrays)
  raise DataError so the CLI can report them cleanly with exit code 2.
- Per-record errors (missing fields, nonsensical values, duplicates)
  are skipped or normalised and a warning is recorded, so the tool never crashes.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from .models import Node, VM

# A node with less than 16 MiB of RAM is almost certainly bad data (missing zeros...).
# The smallest real Proxmox node needs several GB.
MIN_PLAUSIBLE_MEM_TOTAL = 16 * 1024 * 1024


class DataError(Exception):
    """Unrecoverable error while reading the data."""


@dataclass
class Dataset:
    cluster: str
    collected_at: str | None
    nodes: list[Node] = field(default_factory=list)
    vms: list[VM] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _as_int(value: object) -> int | None:
    """Coerce to int, rejecting bools and garbage strings."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            return None
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def _parse_node(raw: object, index: int, seen: set[str], warnings: list[str]) -> Node | None:
    where = f"nodes[{index}]"
    if not isinstance(raw, dict):
        warnings.append(f"{where}: not an object, skipped")
        return None

    name = raw.get("node") or raw.get("name")
    if not isinstance(name, str) or not name.strip():
        warnings.append(f"{where}: missing node name (`node`), skipped")
        return None
    name = name.strip()
    if name in seen:
        warnings.append(f"{where}: duplicate node '{name}', skipped later record")
        return None
    seen.add(name)

    status = str(raw.get("status") or "unknown").strip().lower()
    if status not in ("online", "offline"):
        warnings.append(f"{where} ({name}): unusual status '{status}', treated as not online")

    cpu_cores = _as_int(raw.get("cpu_cores", raw.get("maxcpu")))
    if cpu_cores is None or cpu_cores <= 0:
        warnings.append(f"{where} ({name}): invalid cpu_cores ({raw.get('cpu_cores')!r}), left blank")
        cpu_cores = None

    mem_total = _as_int(raw.get("mem_total", raw.get("maxmem")))
    if mem_total is None or mem_total <= 0:
        warnings.append(f"{where} ({name}): invalid mem_total ({raw.get('mem_total')!r}), left blank")
        mem_total = None
    elif mem_total < MIN_PLAUSIBLE_MEM_TOTAL:
        warnings.append(
            f"{where} ({name}): mem_total={mem_total} bytes is implausibly small, "
            f"treated as bad data and left blank"
        )
        mem_total = None

    note = raw.get("note")
    return Node(
        name=name,
        status=status,
        cpu_cores=cpu_cores,
        mem_total=mem_total,
        note=str(note) if note else None,
    )


def _parse_vm(
    raw: object,
    index: int,
    seen_vmids: dict[int, str],
    warnings: list[str],
) -> VM | None:
    where = f"vms[{index}]"
    if not isinstance(raw, dict):
        warnings.append(f"{where}: not an object, skipped")
        return None

    vmid = _as_int(raw.get("vmid"))
    if vmid is None:
        warnings.append(f"{where}: missing or unreadable `vmid`, skipped")
        return None

    name = str(raw.get("name") or f"vm-{vmid}")
    node = raw.get("node")
    if not isinstance(node, str) or not node.strip():
        warnings.append(f"vmid={vmid} ({name}): missing `node`, skipped")
        return None
    node = node.strip()

    # vmid is unique within a cluster. A duplicate usually means the snapshot was
    # duplicated, so keep the first record to avoid double counting.
    if vmid in seen_vmids:
        warnings.append(
            f"vmid={vmid} ({name}): duplicate vmid with record on node "
            f"'{seen_vmids[vmid]}', skipped this record"
        )
        return None
    seen_vmids[vmid] = node

    status = str(raw.get("status") or "unknown").strip().lower()

    vcpus = _as_int(raw.get("vcpus", raw.get("maxcpu")))
    if vcpus is None or vcpus < 0:
        warnings.append(f"vmid={vmid} ({name}): invalid vcpus ({raw.get('vcpus')!r}), treated as 0")
        vcpus = 0

    cpu_raw = _as_float(raw.get("cpu_usage", raw.get("cpu")))
    if cpu_raw is None:
        warnings.append(f"vmid={vmid} ({name}): missing cpu_usage, treated as 0")
        cpu_usage = 0.0
    elif cpu_raw < 0:
        warnings.append(f"vmid={vmid} ({name}): negative cpu_usage={cpu_raw}, treated as 0")
        cpu_usage = 0.0
    elif cpu_raw <= 1.0:
        cpu_usage = cpu_raw
    elif cpu_raw <= 100.0:
        # The spec says 0..1, but some records are stored as a percent.
        warnings.append(
            f"vmid={vmid} ({name}): cpu_usage={cpu_raw:g} outside 0..1 range, "
            f"interpreted as {cpu_raw:g}% and normalised to {cpu_raw / 100:g}"
        )
        cpu_usage = cpu_raw / 100.0
    else:
        # Do not clamp to 1.0: that would produce pretty but wrong numbers.
        warnings.append(f"vmid={vmid} ({name}): cpu_usage={cpu_raw:g} > 100, invalid, treated as 0")
        cpu_usage = 0.0

    mem_max = _as_int(raw.get("mem_max", raw.get("maxmem")))
    if mem_max is not None and mem_max <= 0:
        warnings.append(f"vmid={vmid} ({name}): invalid mem_max={mem_max}, left blank")
        mem_max = None

    mem_used = _as_int(raw.get("mem_used", raw.get("mem")))
    if mem_used is not None and mem_used < 0:
        warnings.append(f"vmid={vmid} ({name}): negative mem_used={mem_used}, treated as unknown")
        mem_used = None
    if mem_used is None and status == "running":
        warnings.append(
            f"vmid={vmid} ({name}): empty mem_used, RAM used treated as unknown "
            f"(not added to total, not eligible for migration)"
        )
    if mem_used is not None and mem_max is not None and mem_used > mem_max:
        warnings.append(
            f"vmid={vmid} ({name}): mem_used ({mem_used}) larger than mem_max ({mem_max}), kept as-is"
        )

    return VM(
        vmid=vmid,
        name=name,
        node=node,
        status=status,
        vcpus=vcpus,
        cpu_usage=cpu_usage,
        mem_max=mem_max,
        mem_used=mem_used,
    )


def load_dataset(path: str | Path) -> Dataset:
    """Read and validate the snapshot file."""
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise DataError(f"file not found: {file_path}") from exc
    except OSError as exc:
        raise DataError(f"cannot read file {file_path}: {exc}") from exc

    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DataError(
            f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(document, dict):
        raise DataError("JSON file must be an object at the top level")

    raw_nodes = document.get("nodes")
    raw_vms = document.get("vms")
    if not isinstance(raw_nodes, list):
        raise DataError("missing `nodes` array (or wrong type)")
    if not isinstance(raw_vms, list):
        raise DataError("missing `vms` array (or wrong type)")

    warnings: list[str] = []
    collected_at = document.get("collected_at")
    dataset = Dataset(
        cluster=str(document.get("cluster") or "unknown"),
        collected_at=str(collected_at) if collected_at else None,
        warnings=warnings,
    )

    seen_nodes: set[str] = set()
    for index, raw in enumerate(raw_nodes):
        node = _parse_node(raw, index, seen_nodes, warnings)
        if node is not None:
            dataset.nodes.append(node)
    if not dataset.nodes:
        raise DataError("no valid node found in the file")

    seen_vmids: dict[int, str] = {}
    for index, raw in enumerate(raw_vms):
        vm = _parse_vm(raw, index, seen_vmids, warnings)
        if vm is not None:
            dataset.vms.append(vm)

    # VMs on nodes that do not appear in `nodes` (e.g. a node removed from the
    # cluster while the snapshot still lists its VMs) -> warn and skip in load.
    known_nodes = {node.name for node in dataset.nodes}
    unknown: dict[str, int] = {}
    for vm in dataset.vms:
        if vm.node not in known_nodes:
            unknown[vm.node] = unknown.get(vm.node, 0) + 1
    for node_name, count in sorted(unknown.items()):
        warnings.append(
            f"{count} VM(s) belong to node '{node_name}' not listed in `nodes`, "
            f"not counted in node load"
        )

    return dataset
