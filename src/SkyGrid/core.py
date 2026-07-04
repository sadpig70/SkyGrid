#!/usr/bin/env python3
"""Deterministic power-compute-satellite provenance scoring for SkyGrid (stdlib only).

SkyGrid is a "power-compute-satellite attestation mesh" that recomposes three
primitives:

  * WattMesh  -- home energy negotiation (renewable availability)
  * OrbiRoam  -- orbital tasking attestation (satellite-confirmed renewable)
  * PowerRoam -- mobile compute roaming (select the best powered location)

Domain: Energy / Space.

The core exposes four deterministic functions over JSON-shaped dicts:

  evaluate_power_availability -- score one location vs a satellite attestation
  plan_compute_roaming        -- pick the best power source for a compute demand
  verify_provenance           -- check a roaming plan against a satellite chain
  render_report               -- render a Markdown report for a roaming plan
"""

import copy

RENEWABLE_THRESHOLD_PCT = 50
LATENCY_REFERENCE_MS = 200


def _require_non_negative(name, value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{name} must be a number")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _require_location(location):
    if not isinstance(location, dict):
        raise TypeError("location must be a dict")
    for field in ("name", "grid_capacity_mw", "renewable_pct", "latency_ms"):
        if field not in location:
            raise ValueError(f"location missing fields: {field}")
    _require_non_negative("grid_capacity_mw", location["grid_capacity_mw"])
    _require_non_negative("renewable_pct", location["renewable_pct"])
    if location["renewable_pct"] > 100:
        raise ValueError("renewable_pct must be within [0, 100]")
    _require_non_negative("latency_ms", location["latency_ms"])


def _require_attestation(attestation):
    if not isinstance(attestation, dict):
        raise TypeError("satellite_attestation must be a dict")
    for field in ("tasking_id", "confirmed_renewable", "evidence_hash"):
        if field not in attestation:
            raise ValueError(f"satellite_attestation missing fields: {field}")
    if not isinstance(attestation["confirmed_renewable"], bool):
        raise TypeError("confirmed_renewable must be a bool")


def evaluate_power_availability(location, satellite_attestation):
    """Score one location against a satellite renewable attestation.

    location: {name, grid_capacity_mw, renewable_pct, latency_ms}
    satellite_attestation: {tasking_id, confirmed_renewable, timestamp, evidence_hash}

    Returns a deterministic dict with verified_renewable, power_score,
    latency_penalty, availability_score, and satellite_verified.
    """
    location = copy.deepcopy(location)
    satellite_attestation = copy.deepcopy(satellite_attestation)
    _require_location(location)
    _require_attestation(satellite_attestation)

    satellite_confirmed = bool(satellite_attestation.get("confirmed_renewable", False))
    renewable_pct = location.get("renewable_pct", 0)
    grid_capacity_mw = location.get("grid_capacity_mw", 0)
    latency_ms = location.get("latency_ms", 0)

    verified_renewable = satellite_confirmed and renewable_pct >= RENEWABLE_THRESHOLD_PCT
    power_score = grid_capacity_mw * (renewable_pct / 100)
    latency_penalty = max(0, 1 - latency_ms / LATENCY_REFERENCE_MS)
    availability_score = power_score * latency_penalty

    return {
        "location": location,
        "tasking_id": satellite_attestation.get("tasking_id", ""),
        "evidence_hash": satellite_attestation.get("evidence_hash", ""),
        "verified_renewable": verified_renewable,
        "power_score": power_score,
        "latency_penalty": latency_penalty,
        "availability_score": availability_score,
        "satellite_verified": satellite_confirmed,
    }


def plan_compute_roaming(demand, power_sources):
    """Select the best power source for a compute demand.

    demand: {workload_tflops, duration_hours, max_latency_ms}
    power_sources: list of {location, satellite_attestation}

    Each source is scored via evaluate_power_availability. A source is eligible
    only when renewable evidence is verified and latency is within demand.

    Returns {selected_location, availability_score, allocation_tflop_hours, all_scores}.
    """
    demand = copy.deepcopy(demand)
    power_sources = copy.deepcopy(power_sources)
    if not isinstance(demand, dict):
        raise TypeError("demand must be a dict")
    for field in ("workload_tflops", "duration_hours", "max_latency_ms"):
        if field not in demand:
            raise ValueError(f"demand missing fields: {field}")
        _require_non_negative(field, demand[field])
    if not isinstance(power_sources, list):
        raise TypeError("power_sources must be a list")

    all_scores = []
    best = None
    best_score = None
    max_latency_ms = demand["max_latency_ms"]
    for source in power_sources:
        location = source.get("location", {})
        attestation = source.get("satellite_attestation", {})
        scored = evaluate_power_availability(location, attestation)
        latency_ok = scored["location"].get("latency_ms", 0) <= max_latency_ms
        eligible = scored["verified_renewable"] and latency_ok
        rejection_reason = ""
        if not scored["verified_renewable"]:
            rejection_reason = "renewable_not_verified"
        elif not latency_ok:
            rejection_reason = "latency_exceeds_demand"
        entry = {
            "location": location.get("name", ""),
            "tasking_id": scored["tasking_id"],
            "evidence_hash": scored["evidence_hash"],
            "verified_renewable": scored["verified_renewable"],
            "latency_ms": scored["location"].get("latency_ms", 0),
            "latency_ok": latency_ok,
            "eligible": eligible,
            "rejection_reason": rejection_reason,
            "power_score": scored["power_score"],
            "latency_penalty": scored["latency_penalty"],
            "availability_score": scored["availability_score"],
        }
        all_scores.append(entry)
        if eligible and (best_score is None or scored["availability_score"] > best_score):
            best_score = scored["availability_score"]
            best = scored

    if best is None:
        selected_location = None
        selected_tasking_id = None
        selected_evidence_hash = None
        availability_score = 0.0
    else:
        selected_location = best["location"].get("name", "")
        selected_tasking_id = best["tasking_id"]
        selected_evidence_hash = best["evidence_hash"]
        availability_score = best["availability_score"]

    workload_tflops = demand.get("workload_tflops", 0)
    duration_hours = demand.get("duration_hours", 0)
    allocation_tflop_hours = workload_tflops * duration_hours

    return {
        "selected_location": selected_location,
        "selected_tasking_id": selected_tasking_id,
        "selected_evidence_hash": selected_evidence_hash,
        "availability_score": availability_score,
        "allocation_tflop_hours": allocation_tflop_hours,
        "all_scores": all_scores,
    }


def verify_provenance(roaming_plan, satellite_chain):
    """Verify a roaming plan against a satellite evidence chain.

    roaming_plan: output of plan_compute_roaming
    satellite_chain: list of {tasking_id, evidence_hash, confirmed}

    provenance is valid only when the selected tasking/evidence pair is present
    in the confirmed satellite chain.
    """
    roaming_plan = copy.deepcopy(roaming_plan)
    satellite_chain = copy.deepcopy(satellite_chain)

    selected = roaming_plan.get("selected_location")
    selected_tasking_id = roaming_plan.get("selected_tasking_id")
    selected_evidence_hash = roaming_plan.get("selected_evidence_hash")
    selected_link = None
    for link in satellite_chain:
        if (
            link.get("tasking_id") == selected_tasking_id
            and link.get("evidence_hash") == selected_evidence_hash
        ):
            selected_link = link
            break
    selected_link_confirmed = bool(selected_link and selected_link.get("confirmed", False))
    provenance_valid = selected is not None and selected_link_confirmed

    return {
        "provenance_valid": provenance_valid,
        "chain_length": len(satellite_chain),
        "selected_location": selected,
        "selected_tasking_id": selected_tasking_id,
        "selected_evidence_hash": selected_evidence_hash,
        "selected_link_confirmed": selected_link_confirmed,
        "satellite_verified": selected_link_confirmed,
    }


def render_report(result):
    """Render a Markdown report for a roaming plan (output of plan_compute_roaming)."""
    selected = result.get("selected_location")
    availability_score = result.get("availability_score", 0)
    allocation = result.get("allocation_tflop_hours", 0)
    all_scores = result.get("all_scores", [])

    lines = [
        "# SkyGrid Compute Roaming Report",
        "",
        f"- selected_location: {selected if selected is not None else '(none)'}",
        f"- selected_tasking_id: {result.get('selected_tasking_id') or '(none)'}",
        f"- selected_evidence_hash: {result.get('selected_evidence_hash') or '(none)'}",
        f"- availability_score: {availability_score}",
        f"- allocation: {allocation} TFLOP-hours",
        "",
        "## Power Source Scores",
        "",
        "| location | eligible | rejection_reason | power_score | latency_penalty | availability_score | verified_renewable |",
        "|---|---|---|---|---|---|---|",
    ]
    for entry in all_scores:
        lines.append(
            f"| {entry['location']} | {entry['eligible']} | {entry['rejection_reason']} "
            f"| {entry['power_score']} | {entry['latency_penalty']} "
            f"| {entry['availability_score']} | {entry['verified_renewable']} |"
        )
    lines.append("")
    return "\n".join(lines)
