"""Compute per-node load and evaluate it against the thresholds."""

from __future__ import annotations

from collections import defaultdict

from .models import Node, NodeEvaluation, NodeLoad, Thresholds, VM


def compute_loads(nodes: list[Node], vms: list[VM]) -> dict[str, NodeLoad]:
    """Group VMs by node and compute the load metrics.

    Only `running` VMs count toward current load. `stopped` VMs are still counted
    separately because they keep their allocated vCPU/RAM.
    """
    by_node: dict[str, list[VM]] = defaultdict(list)
    known = {node.name for node in nodes}
    for vm in vms:
        if vm.node in known:
            by_node[vm.node].append(vm)

    loads: dict[str, NodeLoad] = {}
    for node in nodes:
        node_vms = by_node.get(node.name, [])
        running = [vm for vm in node_vms if vm.is_running]
        stopped = [vm for vm in node_vms if not vm.is_running]
        loads[node.name] = NodeLoad(
            node=node,
            running_vms=len(running),
            stopped_vms=len(stopped),
            vcpus_running=sum(vm.vcpus for vm in running),
            vcpus_stopped=sum(vm.vcpus for vm in stopped),
            cpu_used_cores=sum(vm.cpu_cores_used for vm in running),
            mem_used_bytes=sum((vm.mem_used or 0) for vm in running),
            unknown_mem_vms=sum(1 for vm in running if vm.mem_used is None),
        )
    return loads


def evaluate(load: NodeLoad, thresholds: Thresholds) -> NodeEvaluation:
    """Compare a node's load with the thresholds; return reasons and warnings."""
    reasons: list[str] = []
    warnings: list[str] = []
    node = load.node

    if not node.is_online:
        warnings.append(f"node {node.name} is {node.status}, not eligible as a migration target")

    if load.cpu_pct is not None and load.cpu_pct >= thresholds.cpu_pct:
        reasons.append(f"CPU {load.cpu_pct:.1f}% >= {thresholds.cpu_pct:.1f}%")

    if load.mem_pct is not None and load.mem_pct >= thresholds.mem_pct:
        reasons.append(f"RAM {load.mem_pct:.1f}% >= {thresholds.mem_pct:.1f}%")

    if load.mem_pct is None:
        warnings.append(f"node {node.name}: no valid mem_total, cannot compute RAM %")

    if load.overcommit is not None and load.overcommit >= thresholds.overcommit:
        warnings.append(
            f"node {node.name}: vCPU overcommit {load.overcommit:.2f} >= "
            f"{thresholds.overcommit:.2f}, risk if all VMs run at full capacity"
        )

    if load.unknown_mem_vms:
        warnings.append(
            f"node {node.name}: {load.unknown_mem_vms} VM(s) missing mem_used, "
            f"actual RAM may be higher than shown"
        )

    return NodeEvaluation(load=load, reasons=reasons, warnings=warnings)


def evaluate_all(
    loads: dict[str, NodeLoad], thresholds: Thresholds
) -> dict[str, NodeEvaluation]:
    return {name: evaluate(load, thresholds) for name, load in loads.items()}
