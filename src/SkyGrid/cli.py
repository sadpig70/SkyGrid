#!/usr/bin/env python3
"""CLI for SkyGrid."""

import argparse
import json
import sys

from .core import (
    evaluate_power_availability,
    plan_compute_roaming,
    render_report,
    verify_provenance,
)
from .samples import write_samples


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _dump_json(doc, path=None):
    text = json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)


def cmd_sample(args):
    written = write_samples(args.out)
    _dump_json({"written": written})
    return 0


def cmd_evaluate(args):
    doc = _load_json(args.input)
    result = evaluate_power_availability(doc["location"], doc["satellite_attestation"])
    _dump_json(result, args.out)
    return 0


def cmd_route(args):
    doc = _load_json(args.input)
    result = plan_compute_roaming(doc["demand"], doc["power_sources"])
    _dump_json(result, args.out)
    return 0


def cmd_verify(args):
    doc = _load_json(args.input)
    result = verify_provenance(doc["roaming_plan"], doc["satellite_chain"])
    _dump_json(result, args.out)
    return 0 if result["provenance_valid"] else 1


def cmd_report(args):
    doc = _load_json(args.input)
    text = render_report(doc)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="sky-grid")
    sub = p.add_subparsers(dest="cmd", required=True)

    sample = sub.add_parser("sample", help="emit deterministic power-source / demand / satellite-chain fixtures")
    sample.add_argument("--out", default="examples")
    sample.set_defaults(func=cmd_sample)

    evaluate = sub.add_parser("evaluate", help="score one location against a satellite attestation")
    evaluate.add_argument("--input", required=True)
    evaluate.add_argument("--out")
    evaluate.set_defaults(func=cmd_evaluate)

    route = sub.add_parser("route", help="plan compute roaming across power sources")
    route.add_argument("--input", required=True)
    route.add_argument("--out")
    route.set_defaults(func=cmd_route)

    verify = sub.add_parser("verify", help="verify provenance of a roaming plan against a satellite chain")
    verify.add_argument("--input", required=True)
    verify.add_argument("--out")
    verify.set_defaults(func=cmd_verify)

    report = sub.add_parser("report", help="render a Markdown report for a roaming plan")
    report.add_argument("--input", required=True)
    report.add_argument("--out")
    report.set_defaults(func=cmd_report)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)
