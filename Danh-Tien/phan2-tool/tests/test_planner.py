"""Tests for the migration planner."""

from __future__ import annotations

import unittest

from pve_balance.metrics import compute_loads
from pve_balance.models import Node, Thresholds, VM
from pve_balance.planner import plan_migrations

GIB = 1024**3
THRESHOLDS = Thresholds(cpu_pct=80, mem_pct=85, overcommit=2.0)


def node(name: str, cores: int = 8, mem_gib: int = 64, status: str = "online") -> Node:
    return Node(name=name, status=status, cpu_cores=cores, mem_total=mem_gib * GIB)


def vm(
    vmid: int,
    node_name: str,
    vcpus: int,
    usage: float,
    mem_gib: float | None,
    status: str = "running",
) -> VM:
    return VM(
        vmid=vmid,
        name=f"vm-{vmid}",
        node=node_name,
        status=status,
        vcpus=vcpus,
        cpu_usage=usage,
        mem_max=None if mem_gib is None else int(mem_gib * GIB),
        mem_used=None if mem_gib is None else int(mem_gib * GIB),
    )


def run_plan(nodes: list[Node], vms: list[VM], thresholds: Thresholds = THRESHOLDS):
    loads = compute_loads(nodes, vms)
    return plan_migrations(loads, vms, thresholds)


class PlanTests(unittest.TestCase):
    def test_overloaded_node_is_relieved_without_overloading_target(self):
        nodes = [node("n1"), node("n2")]
        vms = [
            vm(1, "n1", vcpus=4, usage=0.5, mem_gib=40),
            vm(2, "n1", vcpus=2, usage=0.2, mem_gib=20),
            vm(3, "n2", vcpus=4, usage=0.3, mem_gib=10),
        ]
        plan = run_plan(nodes, vms)

        self.assertEqual(plan.unresolved, [])
        self.assertEqual(len(plan.migrations), 1)
        move = plan.migrations[0]
        self.assertEqual(move.source, "n1")
        self.assertEqual(move.target, "n2")
        self.assertLess(move.source_after.mem_pct or 0, THRESHOLDS.mem_pct)
        self.assertLess(move.source_after.cpu_pct or 0, THRESHOLDS.cpu_pct)
        self.assertLess(move.target_after.mem_pct or 0, THRESHOLDS.mem_pct)
        self.assertLess(move.target_after.cpu_pct or 0, THRESHOLDS.cpu_pct)
        self.assertLess(move.target_after.overcommit or 0, THRESHOLDS.overcommit)

    def test_no_move_when_target_would_be_overloaded(self):
        nodes = [node("n1"), node("n2")]
        vms = [
            vm(1, "n1", vcpus=4, usage=0.1, mem_gib=40),
            vm(2, "n1", vcpus=4, usage=0.1, mem_gib=20),
            vm(3, "n2", vcpus=4, usage=0.1, mem_gib=50),
        ]
        plan = run_plan(nodes, vms)

        self.assertEqual(plan.migrations, [])
        self.assertEqual(plan.unresolved, ["n1"])
        self.assertTrue(any("n1" in note for note in plan.notes))

    def test_offline_node_is_not_a_target(self):
        nodes = [node("n1"), node("n2", status="offline")]
        vms = [vm(1, "n1", vcpus=4, usage=0.5, mem_gib=60)]
        plan = run_plan(nodes, vms)

        self.assertEqual(plan.migrations, [])
        self.assertEqual(plan.unresolved, ["n1"])

    def test_nothing_to_do_when_all_nodes_are_safe(self):
        nodes = [node("n1"), node("n2")]
        vms = [
            vm(1, "n1", vcpus=4, usage=0.2, mem_gib=10),
            vm(2, "n2", vcpus=4, usage=0.2, mem_gib=10),
        ]
        plan = run_plan(nodes, vms)

        self.assertEqual(plan.migrations, [])
        self.assertEqual(plan.unresolved, [])

    def test_vm_with_unknown_memory_is_not_migrated(self):
        nodes = [node("n1"), node("n2")]
        vms = [
            vm(1, "n1", vcpus=4, usage=0.5, mem_gib=40),
            vm(2, "n1", vcpus=2, usage=0.1, mem_gib=None),
            vm(3, "n1", vcpus=2, usage=0.1, mem_gib=20),
        ]
        plan = run_plan(nodes, vms)

        self.assertEqual(len(plan.migrations), 1)
        self.assertNotEqual(plan.migrations[0].vm.vmid, 2)
        self.assertTrue(any("vmid=2" in note for note in plan.notes))

    def test_target_overcommit_threshold_blocks_move(self):
        nodes = [node("n1"), node("n2")]
        vms = [
            vm(1, "n1", vcpus=4, usage=0.1, mem_gib=20),
            vm(2, "n1", vcpus=4, usage=0.1, mem_gib=40),
            # n2 already allocates 15/8 vCPU, any added VM exceeds the 2.0 limit
            vm(3, "n2", vcpus=3, usage=0.01, mem_gib=2),
            vm(4, "n2", vcpus=3, usage=0.01, mem_gib=2),
            vm(5, "n2", vcpus=3, usage=0.01, mem_gib=2),
            vm(6, "n2", vcpus=3, usage=0.01, mem_gib=2),
            vm(7, "n2", vcpus=3, usage=0.01, mem_gib=2),
        ]
        plan = run_plan(nodes, vms)

        self.assertEqual(plan.migrations, [])
        self.assertEqual(plan.unresolved, ["n1"])

    def test_plan_is_deterministic(self):
        nodes = [node("n1"), node("n2"), node("n3")]
        vms = [
            vm(1, "n1", vcpus=4, usage=0.5, mem_gib=40),
            vm(2, "n1", vcpus=2, usage=0.2, mem_gib=20),
            vm(3, "n2", vcpus=4, usage=0.3, mem_gib=10),
            vm(4, "n3", vcpus=4, usage=0.3, mem_gib=10),
        ]
        first = run_plan(nodes, vms)
        second = run_plan(nodes, vms)
        self.assertEqual(
            [(m.vm.vmid, m.source, m.target) for m in first.migrations],
            [(m.vm.vmid, m.source, m.target) for m in second.migrations],
        )

    def test_no_vm_is_moved_twice(self):
        nodes = [node("n1"), node("n2"), node("n3")]
        vms = [
            vm(1, "n1", vcpus=4, usage=0.5, mem_gib=40),
            vm(2, "n1", vcpus=4, usage=0.5, mem_gib=40),
            vm(3, "n2", vcpus=4, usage=0.3, mem_gib=10),
            vm(4, "n3", vcpus=4, usage=0.3, mem_gib=10),
        ]
        plan = run_plan(nodes, vms)
        vmids = [m.vm.vmid for m in plan.migrations]
        self.assertEqual(len(vmids), len(set(vmids)))


if __name__ == "__main__":
    unittest.main()
