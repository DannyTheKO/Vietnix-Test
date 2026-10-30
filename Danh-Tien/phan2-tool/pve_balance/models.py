"""Core data types.

Separated from JSON loading and computation so that:
- the code is easier to read,
- unit tests do not need a real JSON file,
- we avoid passing loose dicts around.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Node:
    """A physical node in the cluster."""

    name: str
    status: str
    # None means the data is missing/invalid, not zero
    cpu_cores: int | None
    mem_total: int | None
    note: str | None = None

    @property
    def is_online(self) -> bool:
        return self.status == "online"

    @property
    def has_valid_cpu(self) -> bool:
        return self.cpu_cores is not None and self.cpu_cores > 0

    @property
    def has_valid_mem(self) -> bool:
        return self.mem_total is not None and self.mem_total > 0


@dataclass(frozen=True)
class VM:
    """A virtual machine (or container) in the cluster."""

    vmid: int
    name: str
    node: str
    status: str
    vcpus: int
    # Normalised to the 0..1 range (source data may be recorded as a percent)
    cpu_usage: float
    mem_max: int | None
    mem_used: int | None

    @property
    def is_running(self) -> bool:
        return self.status == "running"

    @property
    def cpu_cores_used(self) -> float:
        """Physical cores the VM is using (estimate).

        cpu_usage is a fraction of the *allocated* vCPUs, so it must be multiplied
        by vcpus before dividing by the node's physical core count.
        """
        return self.vcpus * self.cpu_usage


@dataclass(frozen=True)
class Thresholds:
    """Evaluation thresholds. These are assumptions and must be documented."""

    cpu_pct: float = 80.0
    mem_pct: float = 85.0
    overcommit: float = 2.0


@dataclass
class NodeLoad:
    """Current load of a node, counting only running VMs."""

    node: Node
    running_vms: int
    stopped_vms: int
    vcpus_running: int
    vcpus_stopped: int
    cpu_used_cores: float
    mem_used_bytes: int
    # Running VMs missing mem_used: actual RAM may be higher
    unknown_mem_vms: int = 0

    @property
    def cpu_pct(self) -> float | None:
        if not self.node.has_valid_cpu:
            return None
        return self.cpu_used_cores / self.node.cpu_cores * 100.0

    @property
    def mem_pct(self) -> float | None:
        if not self.node.has_valid_mem:
            return None
        return self.mem_used_bytes / self.node.mem_total * 100.0

    @property
    def overcommit(self) -> float | None:
        if not self.node.has_valid_cpu:
            return None
        return self.vcpus_running / self.node.cpu_cores


@dataclass
class NodeEvaluation:
    """Result of evaluating a node against the thresholds."""

    load: NodeLoad
    reasons: list[str]  # why the node is considered overloaded
    warnings: list[str]  # secondary warnings (offline, overcommit, missing data)

    @property
    def name(self) -> str:
        return self.load.node.name

    @property
    def overloaded(self) -> bool:
        return bool(self.reasons)
