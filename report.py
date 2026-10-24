#!/usr/bin/env python3
"""Render an offline comparison dashboard from Stream Meter JSON files."""
import argparse
import json
import math
from pathlib import Path
import statistics


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def quantile(values, fraction):
    values = sorted(v for v in values if number(v))
    if not values:
        return None
    index = (len(values) - 1) * fraction
    low, high = math.floor(index), math.ceil(index)
    return values[low] + (values[high] - values[low]) * (index - low)


def validate_prices(value):
    if not isinstance(value, dict):
        raise ValueError("Prices must be an object keyed by benchmark label")
    for label, price in value.items():
        if not isinstance(price, dict) or any(not number(price.get(k)) for k in ("input", "output")):
            raise ValueError(f"Price for {label!r} needs nonnegative finite input and output rates")
    return value


def summarize(document, prices):
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("Expected Stream Meter schema_version 1")
    if not isinstance(document.get("synthetic"), bool):
        raise ValueError("An explicit synthetic flag is required")
    runs = document.get("runs")
    if not isinstance(runs, list) or not runs:
        raise ValueError("Expected at least one run")
    for run in runs:
        if not isinstance(run, dict) or run.get("status") not in {"ok", "error"}:
            raise ValueError("Each run must have status ok or error")
        for key in ("ttft_s", "elapsed_s", "end_to_end_tps"):
            if run.get(key) is not None and not number(run[key]):
                raise ValueError(f"Invalid measurement {key}")
    good = [r for r in runs if r["status"] == "ok"]
    label = str(document.get("label", "unnamed"))
    price = prices.get(label)
    costs = []
    if price:
        for run in good:
            usage = run.get("usage") or {}
            if isinstance(usage, dict) and number(usage.get("prompt_tokens")) and number(usage.get("completion_tokens")):
                costs.append((usage["prompt_tokens"] * price["input"] + usage["completion_tokens"] * price["output"]) / 1_000_000)
    return {"label": label, "model": str(document.get("model", "unknown")),
            "synthetic": document["synthetic"], "created_at": document.get("created_at"),
            "concurrency": (document.get("config") or {}).get("concurrency"),
            "prompt_sha256": (document.get("config") or {}).get("prompt_sha256"),
            "max_tokens": (document.get("config") or {}).get("max_tokens"),
            "requests": len(runs), "successes": len(good), "errors": len(runs)-len(good),
            "ttft_p50": quantile([r.get("ttft_s") for r in good], .5),
            "ttft_p95": quantile([r.get("ttft_s") for r in good], .95),
            "elapsed_p50": quantile([r.get("elapsed_s") for r in good], .5),
            "tps_p50": quantile([r.get("end_to_end_tps") for r in good], .5),
            "priced_requests": len(costs), "mean_cost": statistics.fmean(costs) if costs else None,
            "prices": price}


def demo_documents():
    documents = []
    for label, first, total, tokens in [("Example A", .18, 1.2, 150), ("Example B", .32, .8, 150), ("Example C", .12, 1.8, 150)]:
        runs = []
        for factor in [.85, 1.0, 1.1, .95, 1.3]:
            runs.append({"status": "ok", "ttft_s": first*factor, "elapsed_s": total*factor,
                         "end_to_end_tps": tokens/(total*factor),
                         "usage": {"prompt_tokens": 500, "completion_tokens": tokens}})
        documents.append({"schema_version": 1, "synthetic": True, "label": label,
                          "model": "fictional-demo-model", "created_at": "synthetic fixture",
                          "config": {"concurrency": 1, "max_tokens": 256, "prompt_sha256": "synthetic-same-prompt"}, "runs": runs})
    return documents


def render(rows):
    # JSON data is embedded in an HTML script element: escape HTML delimiters.
    data = json.dumps(rows, allow_nan=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return (Path(__file__).parent / "template.html").read_text().replace("__REPORT_DATA__", data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="*", type=Path)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--prices", type=Path, help="USD per million tokens, keyed by benchmark label")
    parser.add_argument("--out", type=Path, default=Path("report.html"))
    args = parser.parse_args()
    if args.demo and args.inputs or not args.demo and not args.inputs:
        parser.error("Choose --demo OR one or more input JSON files")
    try:
        prices = validate_prices(json.loads(args.prices.read_text())) if args.prices else {}
        documents = demo_documents() if args.demo else [json.loads(p.read_text()) for p in args.inputs]
        if args.demo and not prices:
            prices = {"Example A": {"input": .2, "output": .8}, "Example B": {"input": .4, "output": 1.6}, "Example C": {"input": .1, "output": .4}}
        rows = [summarize(doc, prices) for doc in documents]
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(render(rows))
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        parser.error(str(exc))
    print(f"Wrote {args.out}; {len(rows)} experiments. Open it in a browser; no server is needed.")


if __name__ == "__main__":
    main()
