![SkyGrid](assets/SkyGrid_hero.png)

# SkyGrid

> Power-compute-satellite attestation mesh: route mobile compute to satellite-verified renewable power.

## One-sentence pitch

`SkyGrid` answers: *Given a compute demand, which powered location offers the strongest satellite-confirmed renewable availability, and can the orbital evidence chain prove it?*

## Why this matters

SkyGrid recomposes three primitives into one attestation mesh:

- **WattMesh** -- home/regional energy negotiation (how much *renewable* power is available).
- **OrbiRoam** -- orbital tasking attestation (a satellite *confirms* the renewable claim).
- **PowerRoam** -- mobile compute roaming (pick the best location to run the workload).

The result is a deterministic score-and-route decision: every location gets a
`power_score`, a `latency_penalty`, and a combined `availability_score`; the
highest-scoring source is selected, and the choice is only *provenance-valid*
when an unbroken satellite evidence chain confirms the renewable claims.

`SkyGrid` is a stdlib-only CLI and Python package.

## What it is not

- Not an energy market or billing engine.
- Not a real-time grid telemetry collector.
- Not an orbital flight scheduler.
- Not a secret store or evidence archive.

It scores compact JSON fixtures and emits a deterministic routing/provenance document.

## Install / Run

Requires Python 3.10+ and no external packages.

From this project root:

```bash
python -m pip install -e .
python -m SkyGrid sample --out examples
python -m SkyGrid evaluate --input examples/power_sources.json   # use any single {location, satellite_attestation} doc
python -m SkyGrid route    --input examples/route_request.json
python -m SkyGrid verify   --input examples/route_request.json   # needs {roaming_plan, satellite_chain}
python -m SkyGrid report   --input examples/route_request.json --out examples/roaming.report.md
```

The closed loop is:

```
sample -> route -> {report, verify}
```

## Fixture format

- `power_sources` -- list of `{location, satellite_attestation}`.
  - `location`: `{name, grid_capacity_mw, renewable_pct, latency_ms}`.
  - `satellite_attestation`: `{tasking_id, confirmed_renewable, timestamp, evidence_hash}`.
- `demand` -- `{workload_tflops, duration_hours, max_latency_ms}`.
- `satellite_chain` -- list of `{tasking_id, evidence_hash, confirmed}`.
- `route_request` -- combined `{demand, power_sources}` ready for `route`.

## Scoring scheme

For each location (verified renewable needs `confirmed_renewable` and `renewable_pct >= 50`):

- `power_score = grid_capacity_mw * (renewable_pct / 100)`
- `latency_penalty = max(0, 1 - latency_ms / 200)`
- `availability_score = power_score * latency_penalty`

`plan_compute_roaming` selects the source with the highest `availability_score`
and computes `allocation_tflop_hours = workload_tflops * duration_hours`.
`verify_provenance` is valid only when a location was selected and every link in
the satellite chain is `confirmed`.

## Python API

```python
from SkyGrid import (
    evaluate_power_availability,
    plan_compute_roaming,
    verify_provenance,
    render_report,
)

plan = plan_compute_roaming(demand, power_sources)
print(plan["selected_location"], plan["allocation_tflop_hours"])

result = verify_provenance(plan, satellite_chain)
print(result["provenance_valid"])

print(render_report(plan))
```

## Tests

From this project root:

```bash
python -m unittest discover -s tests -q
```

## License

MIT License -- see [LICENSE](LICENSE).
