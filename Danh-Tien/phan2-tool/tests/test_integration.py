"""Integration tests against the assignment's snapshot."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from pve_balance.loader import load_dataset
from pve_balance.metrics import compute_loads, evaluate_all
from pve_balance.models import Thresholds
from pve_balance.planner import plan_migrations

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "cluster-pve-hcm-c3.json"


class BundledSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = load_dataset(DATA)
        cls.loads = compute_loads(cls.dataset.nodes, cls.dataset.vms)
        cls.thresholds = Thresholds()
        cls.evaluations = evaluate_all(cls.loads, cls.thresholds)
        cls.plan = plan_migrations(cls.loads, cls.dataset.vms, cls.thresholds)

    def test_bad_records_are_handled(self):
        n06 = self.loads["hcm-c3-n06"]
        self.assertIsNone(n06.node.mem_total)  # 262144 bytes -> bad data
        self.assertIsNone(n06.mem_pct)
        # 3 cpu_usage records stored as percent
        percent_warnings = [
            warning for warning in self.dataset.warnings if "normalised" in warning
        ]
        self.assertEqual(len(percent_warnings), 3)
        # vmid 2001 duplicated on n01/n02 -> only 1 record remains
        duplicates = [vm for vm in self.dataset.vms if vm.vmid == 2001]
        self.assertEqual(len(duplicates), 1)
        # VM on node n07 does not exist -> warning
        self.assertTrue(any("hcm-c3-n07" in w for w in self.dataset.warnings))

    def test_overloaded_node_and_plan(self):
        self.assertEqual(
            [name for name, ev in self.evaluations.items() if ev.overloaded],
            ["hcm-c3-n01"],
        )
        self.assertTrue(self.plan.migrations)
        self.assertEqual(self.plan.unresolved, [])
        move = self.plan.migrations[0]
        self.assertLess(move.source_after.mem_pct or 0, self.thresholds.mem_pct)
        self.assertLess(move.source_after.cpu_pct or 0, self.thresholds.cpu_pct)
        self.assertLess(move.target_after.mem_pct or 0, self.thresholds.mem_pct)
        self.assertLess(move.target_after.overcommit or 0, self.thresholds.overcommit)


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, "-m", "pve_balance", *args],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )

    def test_json_output_is_pure_json(self):
        result = self.run_cli("-f", "json")
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
        self.assertTrue(result.stdout.startswith(b"{"))
        payload = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(payload["overloaded_nodes"], ["hcm-c3-n01"])
        self.assertTrue(payload["migrations"])

    def test_table_output(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0)
        text = result.stdout.decode("utf-8")
        self.assertIn("MIGRATION PLAN", text)
        self.assertIn("hcm-c3-n01", text)

    def test_broken_file_exits_with_code_2(self):
        result = self.run_cli("-i", "no-such-file.json")
        self.assertEqual(result.returncode, 2)
        self.assertIn("error:", result.stderr.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
