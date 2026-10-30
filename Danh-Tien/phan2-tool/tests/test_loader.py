"""Tests for reading and validating data."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pve_balance.loader import DataError, load_dataset

NODE = {"node": "n1", "status": "online", "cpu_cores": 8, "mem_total": 68719476736}


def load_payload(payload: object):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "snapshot.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return load_dataset(path)


def make_payload(nodes=None, vms=None) -> dict:
    return {
        "cluster": "test-cluster",
        "collected_at": "2026-10-27T09:00:00+07:00",
        "nodes": nodes if nodes is not None else [NODE],
        "vms": vms if vms is not None else [],
    }


class LoaderTests(unittest.TestCase):
    def test_reads_basic_records(self):
        dataset = load_payload(
            make_payload(
                vms=[
                    {
                        "vmid": 100,
                        "name": "vm-a",
                        "node": "n1",
                        "status": "running",
                        "vcpus": 2,
                        "cpu_usage": 0.5,
                        "mem_max": 4294967296,
                        "mem_used": 2147483648,
                    }
                ]
            )
        )
        self.assertEqual(dataset.cluster, "test-cluster")
        self.assertEqual(len(dataset.nodes), 1)
        self.assertEqual(len(dataset.vms), 1)
        self.assertEqual(dataset.vms[0].cpu_cores_used, 1.0)
        self.assertEqual(dataset.warnings, [])

    def test_percent_like_cpu_usage_is_normalised(self):
        dataset = load_payload(
            make_payload(
                vms=[
                    {
                        "vmid": 101,
                        "node": "n1",
                        "status": "running",
                        "vcpus": 4,
                        "cpu_usage": 31.0,
                        "mem_max": 4294967296,
                        "mem_used": 1024,
                    }
                ]
            )
        )
        self.assertAlmostEqual(dataset.vms[0].cpu_usage, 0.31)
        self.assertTrue(any("31" in warning for warning in dataset.warnings))

    def test_cpu_usage_above_100_is_rejected(self):
        dataset = load_payload(
            make_payload(
                vms=[
                    {
                        "vmid": 102,
                        "node": "n1",
                        "status": "running",
                        "vcpus": 4,
                        "cpu_usage": 500,
                        "mem_used": 1024,
                    }
                ]
            )
        )
        self.assertEqual(dataset.vms[0].cpu_usage, 0.0)
        self.assertTrue(any("invalid" in warning for warning in dataset.warnings))

    def test_duplicate_vmid_is_dropped(self):
        vm = {
            "vmid": 200,
            "name": "dup",
            "node": "n1",
            "status": "running",
            "vcpus": 2,
            "cpu_usage": 0.1,
            "mem_used": 1024,
        }
        dataset = load_payload(make_payload(vms=[vm, dict(vm)]))
        self.assertEqual(len(dataset.vms), 1)
        self.assertTrue(any("duplicate vmid" in warning for warning in dataset.warnings))

    def test_implausibly_small_mem_total_is_dropped(self):
        node = dict(NODE, mem_total=262144)
        dataset = load_payload(make_payload(nodes=[node]))
        self.assertIsNone(dataset.nodes[0].mem_total)
        self.assertTrue(any("implausibly small" in warning for warning in dataset.warnings))

    def test_missing_vmid_is_skipped(self):
        dataset = load_payload(
            make_payload(
                vms=[{"node": "n1", "status": "running", "vcpus": 2, "cpu_usage": 0.1}]
            )
        )
        self.assertEqual(dataset.vms, [])
        self.assertTrue(any("vmid" in warning for warning in dataset.warnings))

    def test_null_mem_used_is_kept_as_unknown(self):
        dataset = load_payload(
            make_payload(
                vms=[
                    {
                        "vmid": 300,
                        "node": "n1",
                        "status": "running",
                        "vcpus": 2,
                        "cpu_usage": 0.1,
                        "mem_max": 4294967296,
                        "mem_used": None,
                    }
                ]
            )
        )
        self.assertIsNone(dataset.vms[0].mem_used)
        self.assertTrue(any("mem_used" in warning for warning in dataset.warnings))

    def test_vm_on_unknown_node_is_reported(self):
        dataset = load_payload(
            make_payload(
                vms=[
                    {
                        "vmid": 400,
                        "node": "n9",
                        "status": "running",
                        "vcpus": 2,
                        "cpu_usage": 0.1,
                        "mem_used": 1024,
                    }
                ]
            )
        )
        self.assertEqual(len(dataset.vms), 1)
        self.assertTrue(any("n9" in warning for warning in dataset.warnings))

    def test_broken_json_raises_data_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(DataError):
                load_dataset(path)

    def test_missing_vms_array_raises_data_error(self):
        with self.assertRaises(DataError):
            load_payload({"cluster": "c", "nodes": [NODE]})

    def test_missing_file_raises_data_error(self):
        with self.assertRaises(DataError):
            load_dataset("does-not-exist.json")


if __name__ == "__main__":
    unittest.main()
