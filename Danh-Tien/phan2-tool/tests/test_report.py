"""Tests for report rendering."""

from __future__ import annotations

import json
import unittest

from pve_balance.loader import Dataset
from pve_balance.metrics import compute_loads, evaluate_all
from pve_balance.models import Node, Thresholds, VM
from pve_balance.planner import plan_migrations
from pve_balance.report import human_bytes, render_text, to_json, to_json_dict

GIB = 1024**3


def build():
    nodes = [
        Node("n1", "online", 8, 64 * GIB),
        Node("n2", "online", 8, 64 * GIB),
    ]
    vms = [
        VM(1, "big", "n1", "running", 4, 0.5, 56 * GIB, 52 * GIB),
        VM(2, "small", "n1", "running", 2, 0.2, 16 * GIB, 4 * GIB),
        VM(3, "other", "n2", "running", 4, 0.3, 16 * GIB, 10 * GIB),
    ]
    dataset = Dataset(cluster="lab", collected_at="2026-10-27T09:00:00+07:00")
    dataset.nodes = nodes
    dataset.vms = vms
    dataset.warnings = ["test warning"]
    thresholds = Thresholds()
    loads = compute_loads(nodes, vms)
    evaluations = evaluate_all(loads, thresholds)
    plan = plan_migrations(loads, vms, thresholds)
    return dataset, evaluations, plan, thresholds


class ReportTests(unittest.TestCase):
    def test_human_bytes(self):
        self.assertEqual(human_bytes(1024**3), "1.0 GiB")
        self.assertEqual(human_bytes(None), "n/a")

    def test_json_has_expected_structure(self):
        dataset, evaluations, plan, thresholds = build()
        payload = to_json_dict(dataset, evaluations, plan, thresholds)

        self.assertEqual(payload["cluster"], "lab")
        self.assertEqual(payload["overloaded_nodes"], ["n1"])
        self.assertEqual(len(payload["nodes"]), 2)
        self.assertEqual(len(payload["migrations"]), 1)
        self.assertEqual(payload["unresolved_nodes"], [])
        self.assertIn("thresholds", payload)
        self.assertIn("data_warnings", payload)

    def test_json_is_serialisable(self):
        dataset, evaluations, plan, thresholds = build()
        text = to_json(dataset, evaluations, plan, thresholds)
        parsed = json.loads(text)
        self.assertEqual(parsed["nodes"][0]["node"], "n1")

    def test_text_report_contains_key_sections(self):
        dataset, evaluations, plan, thresholds = build()
        text = render_text(dataset, evaluations, plan, thresholds)
        self.assertIn("OVERLOADED NODES", text)
        self.assertIn("MIGRATION PLAN", text)
        self.assertIn("DATA WARNINGS", text)
        self.assertIn("n1", text)

if __name__ == "__main__":
    unittest.main()
