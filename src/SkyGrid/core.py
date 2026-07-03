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


def evaluate_power_availability(location, satellite_attestation):
    """Score one location against a satellite renewable attestation.

    location: {name, grid_capacity_mw, renewable_pct, latency_ms}
    satellite_attestation: {tasking_id, confirmed_renewable, timestamp, evidence_hash}

    Returns a deterministic dict with verified_renewable, power_score,
    latency_penalty, availability_score, and satellite_verified.
    """
    location = copy.deepcopy(location)
    satellite_attestation = copy.deepcopy(satellite_attestation)

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

    Each source is scored via evaluate_power_availability; the source with the
    highest availability_score is selected. allocation is workload * duration.

    Returns {selected_location, availability_score, allocation_tflop_hours, all_scores}.
    """
    demand = copy.deepcopy(demand)
    power_sources = copy.deepcopy(power_sources)

    all_scores = []
    best = None
    best_score = None
    for source in power_sources:
        location = source.get("location", {})
        attestation = source.get("satellite_attestation", {})
        scored = evaluate_power_availability(location, attestation)
        entry = {
            "location": location.get("name", ""),
            "verified_renewable": scored["verified_renewable"],
            "power_score": scored["power_score"],
            "latency_penalty": scored["latency_penalty"],
            "availability_score": scored["availability_score"],
        }
        all_scores.append(entry)
        if best_score is None or scored["availability_score"] > best_score:
            best_score = scored["availability_score"]
            best = scored

    if best is None:
        selected_location = None
        availability_score = 0.0
    else:
        selected_location = best["location"].get("name", "")
        availability_score = best["availability_score"]

    workload_tflops = demand.get("workload_tflops", 0)
    duration_hours = demand.get("duration_hours", 0)
    allocation_tflop_hours = workload_tflops * duration_hours

    return {
        "selected_location": selected_location,
        "availability_score": availability_score,
        "allocation_tflop_hours": allocation_tflop_hours,
        "all_scores": all_scores,
    }


def verify_provenance(roaming_plan, satellite_chain):
    """Verify a roaming plan against a satellite evidence chain.

    roaming_plan: output of plan_compute_roaming
    satellite_chain: list of {tasking_id, evidence_hash, confirmed}

    provenance is valid only when a location was selected and every link in the
    satellite chain is confirmed.
    """
    roaming_plan = copy.deepcopy(roaming_plan)
    satellite_chain = copy.deepcopy(satellite_chain)

    all_confirmed = all(link.get("confirmed", False) for link in satellite_chain)
    selected = roaming_plan.get("selected_location")
    provenance_valid = selected is not None and all_confirmed

    return {
        "provenance_valid": provenance_valid,
        "chain_length": len(satellite_chain),
        "selected_location": selected,
        "satellite_verified": all_confirmed,
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
        f"- availability_score: {availability_score}",
        f"- allocation: {allocation} TFLOP-hours",
        "",
        "## Power Source Scores",
        "",
        "| location | power_score | latency_penalty | availability_score | verified_renewable |",
        "|---|---|---|---|---|",
    ]
    for entry in all_scores:
        lines.append(
            f"| {entry['location']} | {entry['power_score']} | {entry['latency_penalty']} "
            f"| {entry['availability_score']} | {entry['verified_renewable']} |"
        )
    lines.append("")
    return "\n".join(lines)
