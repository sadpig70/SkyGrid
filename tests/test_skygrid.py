#!/usr/bin/env python3
"""Stdlib-only tests for the standalone SkyGrid package."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

ENV = dict(os.environ, PYTHONPATH="src")

from SkyGrid.samples import samples  # noqa: E402
from SkyGrid.core import (  # noqa: E402
    evaluate_power_availability,
    plan_compute_roaming,
    verify_provenance,
)


class TestEvaluatePowerAvailability(unittest.TestCase):
    def test_deterministic_values(self):
        iceland = samples()["power_sources"][0]
        result = evaluate_power_availability(iceland["location"], iceland["satellite_attestation"])
        self.assertEqual(result["location"]["name"], "Iceland-Geo")
        self.assertTrue(result["verified_renewable"])
        self.assertTrue(result["satellite_verified"])
        self.assertAlmostEqual(result["power_score"], 102.0)
        self.assertAlmostEqual(result["latency_penalty"], 0.85)
        self.assertAlmostEqual(result["availability_score"], 86.7)

    def test_repeated_run_is_deterministic(self):
        iceland = samples()["power_sources"][0]
        a = evaluate_power_availability(iceland["location"], iceland["satellite_attestation"])
        b = evaluate_power_availability(iceland["location"], iceland["satellite_attestation"])
        self.assertEqual(a, b)

    def test_low_renewable_not_verified(self):
        coal = samples()["power_sources"][2]
        result = evaluate_power_availability(coal["location"], coal["satellite_attestation"])
        self.assertFalse(result["verified_renewable"])
        self.assertTrue(result["satellite_verified"])

    def test_unconfirmed_satellite_not_verified(self):
        iceland = samples()["power_sources"][0]
        attestation = dict(iceland["satellite_attestation"])
        attestation["confirmed_renewable"] = False
        result = evaluate_power_availability(iceland["location"], attestation)
        self.assertFalse(result["verified_renewable"])
        self.assertFalse(result["satellite_verified"])


class TestPlanComputeRoaming(unittest.TestCase):
    def test_selects_best_source(self):
        s = samples()
        plan = plan_compute_roaming(s["demand"], s["power_sources"])
        self.assertEqual(plan["selected_location"], "Sahara-Solar")
        self.assertEqual(plan["selected_tasking_id"], "ORB-SA-02")
        self.assertTrue(plan["selected_evidence_hash"])
        self.assertAlmostEqual(plan["availability_score"], 108.0)
        self.assertEqual(plan["allocation_tflop_hours"], 200)
        self.assertEqual(len(plan["all_scores"]), 3)

    def test_selected_has_top_score(self):
        s = samples()
        plan = plan_compute_roaming(s["demand"], s["power_sources"])
        top = max(entry["availability_score"] for entry in plan["all_scores"] if entry["eligible"])
        self.assertAlmostEqual(plan["availability_score"], top)

    def test_rejects_verified_source_over_latency_limit(self):
        s = samples()
        demand = dict(s["demand"])
        demand["max_latency_ms"] = 50
        plan = plan_compute_roaming(demand, s["power_sources"])
        self.assertEqual(plan["selected_location"], "Iceland-Geo")
        sahara = next(e for e in plan["all_scores"] if e["location"] == "Sahara-Solar")
        self.assertFalse(sahara["eligible"])
        self.assertEqual(sahara["rejection_reason"], "latency_exceeds_demand")

    def test_empty_power_sources_yields_no_selection(self):
        plan = plan_compute_roaming(samples()["demand"], [])
        self.assertIsNone(plan["selected_location"])
        self.assertEqual(plan["all_scores"], [])
        self.assertEqual(plan["allocation_tflop_hours"], 200)


class TestVerifyProvenance(unittest.TestCase):
    def _plan(self):
        s = samples()
        return plan_compute_roaming(s["demand"], s["power_sources"])

    def test_confirmed_chain_is_valid(self):
        result = verify_provenance(self._plan(), samples()["satellite_chain_confirmed"])
        self.assertTrue(result["provenance_valid"])
        self.assertEqual(result["chain_length"], 3)
        self.assertTrue(result["satellite_verified"])
        self.assertEqual(result["selected_location"], "Sahara-Solar")
        self.assertEqual(result["selected_tasking_id"], "ORB-SA-02")

    def test_denied_chain_is_invalid(self):
        result = verify_provenance(self._plan(), samples()["satellite_chain_denied"])
        self.assertFalse(result["provenance_valid"])
        self.assertFalse(result["satellite_verified"])

    def test_no_selection_is_invalid_even_if_chain_confirmed(self):
        plan = plan_compute_roaming(samples()["demand"], [])
        result = verify_provenance(plan, samples()["satellite_chain_confirmed"])
        self.assertFalse(result["provenance_valid"])
        self.assertIsNone(result["selected_location"])


class TestCLI(unittest.TestCase):
    def test_sample_evaluate_route(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.check_output(
                [sys.executable, "-m", "SkyGrid", "sample", "--out", d],
                cwd=ROOT, text=True, env=ENV,
            )
            # evaluate on a single power source
            eval_input = os.path.join(d, "evaluate_input.json")
            with open(eval_input, "w", encoding="utf-8") as f:
                json.dump(samples()["power_sources"][0], f, ensure_ascii=False)
            out = subprocess.check_output(
                [sys.executable, "-m", "SkyGrid", "evaluate", "--input", eval_input],
                cwd=ROOT, text=True, env=ENV,
            )
            self.assertTrue(json.loads(out)["verified_renewable"])
            # route on the combined request fixture
            out = subprocess.check_output(
                [sys.executable, "-m", "SkyGrid", "route", "--input", os.path.join(d, "route_request.json")],
                cwd=ROOT, text=True, env=ENV,
            )
            plan = json.loads(out)
            self.assertEqual(plan["selected_location"], "Sahara-Solar")
            self.assertEqual(plan["allocation_tflop_hours"], 200)

    def test_report(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.check_output(
                [sys.executable, "-m", "SkyGrid", "sample", "--out", d],
                cwd=ROOT, text=True, env=ENV,
            )
            route_input = os.path.join(d, "route_request.json")
            plan_path = os.path.join(d, "plan.json")
            subprocess.check_output(
                [sys.executable, "-m", "SkyGrid", "route", "--input", route_input, "--out", plan_path],
                cwd=ROOT, text=True, env=ENV,
            )
            report = subprocess.check_output(
                [sys.executable, "-m", "SkyGrid", "report", "--input", plan_path],
                cwd=ROOT, text=True, env=ENV,
            )
            self.assertIn("# SkyGrid Compute Roaming Report", report)
            self.assertIn("Sahara-Solar", report)

    def test_verify_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.check_output(
                [sys.executable, "-m", "SkyGrid", "sample", "--out", d],
                cwd=ROOT, text=True, env=ENV,
            )
            route_input = os.path.join(d, "route_request.json")
            plan_path = os.path.join(d, "plan.json")
            subprocess.check_output(
                [sys.executable, "-m", "SkyGrid", "route", "--input", route_input, "--out", plan_path],
                cwd=ROOT, text=True, env=ENV,
            )
            with open(plan_path, "r", encoding="utf-8") as f:
                plan_doc = json.load(f)

            for label, chain, expect in (
                ("confirmed", samples()["satellite_chain_confirmed"], True),
                ("denied", samples()["satellite_chain_denied"], False),
            ):
                verify_input = os.path.join(d, f"verify_{label}.json")
                with open(verify_input, "w", encoding="utf-8") as f:
                    json.dump({"roaming_plan": plan_doc, "satellite_chain": chain}, f, ensure_ascii=False)
                proc = subprocess.run(
                    [sys.executable, "-m", "SkyGrid", "verify", "--input", verify_input],
                    cwd=ROOT, text=True, env=ENV, capture_output=True,
                )
                self.assertEqual(proc.returncode, 0 if expect else 1, msg=proc.stderr)
                self.assertEqual(json.loads(proc.stdout)["provenance_valid"], expect)


if __name__ == "__main__":
    unittest.main()
