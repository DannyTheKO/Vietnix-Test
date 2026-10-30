"""Propose a live-migration plan (greedy, not globally optimal).

Idea:
1. Find overloaded nodes, handle the worst one first.
2. For each source node, try every running VM against every target node.
3. A move is valid when:
   - the target is online and has valid CPU/RAM,
   - after receiving the VM the target stays below ALL three limits
     (CPU, RAM, overcommit),
   - the source improves.
4. Prefer moves that resolve the overload immediately, then the ones that remove
   the most source pressure, then the least loaded target.
5. Repeat until no node is overloaded or no safe move exists.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .models import Node, NodeLoad, Thresholds, VM


@dataclass(frozen=True)
class Snapshot:
    """Node load at a point in time, used for before/after output."""

    cpu_pct: float | None
    mem_pct: float | None
    overcommit: float | None
    vcpus: int
    mem_used_bytes: int


@dataclass(frozen=True)
class Migration:
    vm: VM
    source: str
    target: str
    source_before: Snapshot
    source_after: Snapshot
    target_before: Snapshot
    target_after: Snapshot


@dataclass
class Plan:
    migrations: list[Migration]
    unresolved: list[str]  # nodes still overloaded after planning
    notes: list[str]


@dataclass
class _NodeState:
    """A copy of a node's load used to simulate adding/removing VMs."""

    node: Node
    cpu_used: float
    mem_used: int
    vcpus: int

    @classmethod
    def from_load(cls, load: NodeLoad) -> "_NodeState":
        return cls(
            node=load.node,
            cpu_used=load.cpu_used_cores,
            mem_used=load.mem_used_bytes,
            vcpus=load.vcpus_running,
        )

    def clone(self) -> "_NodeState":
        return replace(self)

    def add(self, vm: VM) -> None:
        self.cpu_used += vm.cpu_cores_used
        self.mem_used += vm.mem_used or 0
        self.vcpus += vm.vcpus

    def remove(self, vm: VM) -> None:
        self.cpu_used -= vm.cpu_cores_used
        self.mem_used -= vm.mem_used or 0
        self.vcpus -= vm.vcpus

    def cpu_pct(self) -> float | None:
        if not self.node.has_valid_cpu:
            return None
        return self.cpu_used / self.node.cpu_cores * 100.0

    def mem_pct(self) -> float | None:
        if not self.node.has_valid_mem:
            return None
        return self.mem_used / self.node.mem_total * 100.0

    def overcommit(self) -> float | None:
        if not self.node.has_valid_cpu:
            return None
        return self.vcpus / self.node.cpu_cores

    def snapshot(self) -> Snapshot:
        return Snapshot(
            cpu_pct=self.cpu_pct(),
            mem_pct=self.mem_pct(),
            overcommit=self.overcommit(),
            vcpus=self.vcpus,
            mem_used_bytes=self.mem_used,
        )


def _is_overloaded(state: _NodeState, thresholds: Thresholds) -> bool:
    cpu = state.cpu_pct()
    mem = state.mem_pct()
    return (cpu is not None and cpu >= thresholds.cpu_pct) or (
        mem is not None and mem >= thresholds.mem_pct
    )


def _pressure(state: _NodeState, thresholds: Thresholds) -> float:
    """Load normalised to the thresholds: 1.0 means exactly at the limit."""
    values: list[float] = []
    cpu = state.cpu_pct()
    mem = state.mem_pct()
    if cpu is not None:
        values.append(cpu / thresholds.cpu_pct)
    if mem is not None:
        values.append(mem / thresholds.mem_pct)
    return max(values) if values else 0.0


def _can_host(target: _NodeState, vm: VM, thresholds: Thresholds) -> bool:
    """Can the target accept the VM and still be safe?"""
    if not target.node.is_online:
        return False
    # Refuse if we do not know the total RAM: safety cannot be proven.
    if not (target.node.has_valid_cpu and target.node.has_valid_mem):
        return False

    after = target.clone()
    after.add(vm)
    cpu = after.cpu_pct()
    mem = after.mem_pct()
    overcommit = after.overcommit()
    assert cpu is not None and mem is not None and overcommit is not None
    return (
        cpu < thresholds.cpu_pct
        and mem < thresholds.mem_pct
        and overcommit < thresholds.overcommit
    )


def _best_move(
    source: _NodeState,
    candidates: list[VM],
    states: dict[str, _NodeState],
    thresholds: Thresholds,
    moved: set[int],
) -> tuple[VM, _NodeState] | None:
    """Pick the best move for one source node, or None."""
    source_pressure = _pressure(source, thresholds)
    best: tuple[VM, _NodeState] | None = None
    best_key: tuple | None = None

    for vm in candidates:
        if vm.vmid in moved:
            continue
        # Not enough RAM data to prove the target stays safe.
        if vm.mem_used is None:
            continue

        source_after = source.clone()
        source_after.remove(vm)
        drop = source_pressure - _pressure(source_after, thresholds)
        if drop <= 0:
            continue
        resolves = not _is_overloaded(source_after, thresholds)

        for target in states.values():
            if target.node.name == source.node.name:
                continue
            if not _can_host(target, vm, thresholds):
                continue

            target_after = target.clone()
            target_after.add(vm)
            key = (
                0 if resolves else 1,          # resolving the overload is priority 1
                -drop,                          # remove as much source pressure as possible
                _pressure(target_after, thresholds),  # lighter target is better
                vm.vmid,                        # tie-break for stable output
                target.node.name,
            )
            if best_key is None or key < best_key:
                best_key = key
                best = (vm, target)

    return best


def plan_migrations(
    loads: dict[str, NodeLoad],
    vms: list[VM],
    thresholds: Thresholds,
) -> Plan:
    states = {name: _NodeState.from_load(load) for name, load in loads.items()}
    by_node: dict[str, list[VM]] = {name: [] for name in states}
    notes: list[str] = []

    for vm in vms:
        if vm.is_running and vm.node in states:
            by_node[vm.node].append(vm)
            if vm.mem_used is None:
                notes.append(
                    f"vmid={vm.vmid} ({vm.name}): missing mem_used, not eligible for migration"
                )

    moved: set[int] = set()
    migrations: list[Migration] = []
    # Guard against infinite loops on weird data.
    max_steps = sum(len(items) for items in by_node.values()) + len(states) + 1

    for _ in range(max_steps):
        overloaded = sorted(
            (state for state in states.values() if _is_overloaded(state, thresholds)),
            key=lambda state: (-_pressure(state, thresholds), state.node.name),
        )
        if not overloaded:
            break

        chosen: tuple[VM, _NodeState] | None = None
        for source in overloaded:
            chosen = _best_move(
                source, by_node[source.node.name], states, thresholds, moved
            )
            if chosen is not None:
                break

        if chosen is None:
            for source in overloaded:
                notes.append(
                    f"node {source.node.name}: no safe target node found to relieve overload"
                )
            break

        vm, target = chosen
        source = states[vm.node]
        source_before = source.snapshot()
        target_before = target.snapshot()
        source.remove(vm)
        target.add(vm)
        moved.add(vm.vmid)
        migrations.append(
            Migration(
                vm=vm,
                source=source.node.name,
                target=target.node.name,
                source_before=source_before,
                source_after=source.snapshot(),
                target_before=target_before,
                target_after=target.snapshot(),
            )
        )

    unresolved = [
        state.node.name
        for state in states.values()
        if _is_overloaded(state, thresholds)
    ]
    return Plan(migrations=migrations, unresolved=unresolved, notes=notes)
