#!/usr/bin/env python3
"""Deterministic sample fixtures for SkyGrid."""

import copy
import hashlib
import json


def _digest(label):
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


POWER_SOURCE_ICELAND = {
    "location": {
        "name": "Iceland-Geo",
        "grid_capacity_mw": 120,
        "renewable_pct": 85,
        "latency_ms": 30,
    },
    "satellite_attestation": {
        "tasking_id": "ORB-IC-01",
        "confirmed_renewable": True,
        "timestamp": "2026-07-03T00:00:00+00:00",
        "evidence_hash": _digest("iceland-geo"),
    },
}

POWER_SOURCE_SAHARA = {
    "location": {
        "name": "Sahara-Solar",
        "grid_capacity_mw": 200,
        "renewable_pct": 90,
        "latency_ms": 80,
    },
    "satellite_attestation": {
        "tasking_id": "ORB-SA-02",
        "confirmed_renewable": True,
        "timestamp": "2026-07-03T00:00:00+00:00",
        "evidence_hash": _digest("sahara-solar"),
    },
}

POWER_SOURCE_COALBELT = {
    "location": {
        "name": "Coal-Belt",
        "grid_capacity_mw": 300,
        "renewable_pct": 20,
        "latency_ms": 15,
    },
    "satellite_attestation": {
        "tasking_id": "ORB-CB-03",
        "confirmed_renewable": True,
        "timestamp": "2026-07-03T00:00:00+00:00",
        "evidence_hash": _digest("coal-belt"),
    },
}

POWER_SOURCES = [POWER_SOURCE_ICELAND, POWER_SOURCE_SAHARA, POWER_SOURCE_COALBELT]

COMPUTE_DEMAND = {
    "workload_tflops": 50,
    "duration_hours": 4,
    "max_latency_ms": 100,
}

SATELLITE_CHAIN_CONFIRMED = [
    {"tasking_id": "ORB-IC-01", "evidence_hash": _digest("orb-ic-01"), "confirmed": True},
    {"tasking_id": "ORB-SA-02", "evidence_hash": _digest("orb-sa-02"), "confirmed": True},
    {"tasking_id": "ORB-CB-03", "evidence_hash": _digest("orb-cb-03"), "confirmed": True},
]

SATELLITE_CHAIN_DENIED = [
    {"tasking_id": "ORB-IC-01", "evidence_hash": _digest("orb-ic-01"), "confirmed": True},
    {"tasking_id": "ORB-SA-02", "evidence_hash": _digest("orb-sa-02"), "confirmed": False},
    {"tasking_id": "ORB-CB-03", "evidence_hash": _digest("orb-cb-03"), "confirmed": True},
]


def samples():
    return {
        "power_sources": copy.deepcopy(POWER_SOURCES),
        "demand": copy.deepcopy(COMPUTE_DEMAND),
        "satellite_chain_confirmed": copy.deepcopy(SATELLITE_CHAIN_CONFIRMED),
        "satellite_chain_denied": copy.deepcopy(SATELLITE_CHAIN_DENIED),
        "route_request": {
            "demand": copy.deepcopy(COMPUTE_DEMAND),
            "power_sources": copy.deepcopy(POWER_SOURCES),
        },
    }


def write_samples(out_dir):
    import os

    os.makedirs(out_dir, exist_ok=True)
    written = {}
    for name, doc in samples().items():
        path = os.path.join(out_dir, f"{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        written[name] = path
    return written
