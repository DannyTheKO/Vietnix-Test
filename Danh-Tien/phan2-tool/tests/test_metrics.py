"""Tests for load calculation and threshold evaluation."""

from __future__ import annotations

import unittest

from pve_balance.metrics import compute_loads, evaluate
from pve_balance.models import Node, Thresholds, VM

GIB = 1024**3


def node(name="n1", status="online", cores=8, mem=100 * GIB) -> Node:
    return Node(name=name, status=status, cpu_cores=cores, mem_total=mem)


def vm(
    vmid=1,
    node_name="n1",
    status="running",
    vcpus=4,
    usage=0.5,
    mem_used=10 * GIB,
    mem_max=16 * GIB,
) -> VM:
    return VM(
        vmid=vmid,
        name=f"vm-{vmid}",
        node=node_name,
        status=status,
        vcpus=vcpus,
        cpu_usage=usage,
        mem_max=mem_max,
        mem_used=mem_used,
    )


class ComputeLoadTests(unittest.TestCase):
    def test_cpu_memory_and_overcommit(self):
        loads = compute_loads(
            [node()],
            [
                vm(vmid=1, vcpus=4, usage=0.5, mem_used=10 * GIB),  # 2 core
                vm(vmid=2, vcpus=2, usage=1.0, mem_used=30 * GIB),  # 2 core
            ],
        )
        load = loads["n1"]
        self.assertAlmostEqual(load.cpu_used_cores, 4.0)
        self.assertAlmostEqual(load.cpu_pct or 0, 50.0)
        self.assertEqual(load.mem_used_bytes, 40 * GIB)
        self.assertAlmostEqual(load.mem_pct or 0, 40.0)
        self.assertEqual(load.vcpus_running, 6)
        self.assertAlmostEqual(load.overcommit or 0, 0.75)

    def test_stopped_vm_does_not_count_as_load(self):
        loads = compute_loads(
            [node()],
            [
                vm(vmid=1, status="running", vcpus=4, usage=0.5, mem_used=10 * GIB),
                vm(vmid=2, status="stopped", vcpus=16, usage=0.0, mem_used=0),
            ],
        )
        load = loads["n1"]
        self.assertEqual(load.running_vms, 1)
        self.assertEqual(load.stopped_vms, 1)
        self.assertEqual(load.vcpus_running, 4)
        self.assertEqual(load.vcpus_stopped, 16)
        self.assertEqual(load.mem_used_bytes, 10 * GIB)

    def test_unknown_memory_is_counted_as_zero_but_flagged(self):
        loads = compute_loads([node()], [vm(vmid=1, mem_used=None)])
        self.assertEqual(loads["n1"].mem_used_bytes, 0)
        self.assertEqual(loads["n1"].unknown_mem_vms, 1)

    def test_vm_on_unknown_node_is_ignored(self):
        loads = compute_loads([node()], [vm(vmid=1, node_name="n9")])
        self.assertEqual(loads["n1"].running_vms, 0)

    def test_node_with_invalid_cpu_has_no_percentage(self):
        loads = compute_loads([node(cores=None)], [vm()])  # type: ignore[arg-type]
        self.assertIsNone(loads["n1"].cpu_pct)
        self.assertIsNone(loads["n1"].overcommit)


class EvaluateTests(unittest.TestCase):
    def test_exact_threshold_is_overloaded(self):
        loads = compute_loads(
            [node(cores=8, mem=100 * GIB)],
            [vm(vcpus=8, usage=0.8, mem_used=1 * GIB)],
        )
        evaluation = evaluate(loads["n1"], Thresholds(cpu_pct=80, mem_pct=85))
        self.assertTrue(evaluation.overloaded)
        self.assertTrue(any("CPU" in reason for reason in evaluation.reasons))

    def test_memory_threshold(self):
        loads = compute_loads([node()], [vm(vcpus=1, usage=0.1, mem_used=85 * GIB)])
        evaluation = evaluate(loads["n1"], Thresholds())
        self.assertTrue(evaluation.overloaded)
        self.assertTrue(any("RAM" in reason for reason in evaluation.reasons))

    def test_offline_node_is_warned(self):
        loads = compute_loads([node(status="offline")], [])
        evaluation = evaluate(loads["n1"], Thresholds())
        self.assertFalse(evaluation.overloaded)
        self.assertTrue(any("offline" in warning for warning in evaluation.warnings))

    def test_overcommit_is_warning_not_overload(self):
        loads = compute_loads([node(cores=8)], [vm(vcpus=20, usage=0.01, mem_used=GIB)])
        evaluation = evaluate(loads["n1"], Thresholds())
        self.assertFalse(evaluation.overloaded)
        self.assertTrue(any("overcommit" in warning for warning in evaluation.warnings))


if __name__ == "__main__":
    unittest.main()
