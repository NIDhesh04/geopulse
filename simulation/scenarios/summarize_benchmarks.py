"""Summarize benchmark TSV files. Usage: python3 scenarios/summarize_benchmarks.py RUNS.tsv [...]"""
import csv
import statistics
import sys
from collections import Counter, defaultdict


def read_benchmarks(paths):
    runs = {}
    missions = defaultdict(dict)
    revisions = set()
    for path in paths:
        headers = {}
        with open(path, encoding="utf-8", newline="") as stream:
            for items in csv.reader(stream, delimiter="\t"):
                if not items:
                    continue
                kind = items[0]
                if kind == "# geopulse-m5-v1":
                    revisions.add(items[1].removeprefix("engine="))
                if kind in ("# run", "# mission"):
                    headers[kind[2:]] = items[1:]
                if kind not in ("run", "mission"):
                    continue
                record = dict(zip(headers[kind], items[1:], strict=True))
                key = tuple(record[field] for field in ("fixture", "seed", "horizon", "priority"))
                if kind == "run":
                    if key in runs:
                        raise ValueError(f"Duplicate run: {key}")
                    runs[key] = record
                else:
                    if record["id"] in missions[key]:
                        raise ValueError(f"Duplicate mission: {key}, {record['id']}")
                    missions[key][record["id"]] = record
    if len(revisions) != 1:
        raise ValueError("Provide one engine revision per report")
    if not runs or set(missions).difference(runs):
        raise ValueError("Missing benchmark run records")
    matched_schedules = {}
    for key, run in runs.items():
        pair_key=key[:2]
        if matched_schedules.setdefault(pair_key,run["schedule"]) != run["schedule"]:
            raise ValueError(f"Different external schedules for {pair_key}")
        if len(missions[key]) != int(run["missions"]):
            raise ValueError(f"Incomplete mission rows for {key}")
    return runs, missions, revisions.pop()


def summary(values):
    values = list(values)
    if not values:
        return "—"
    median = statistics.median(values)
    if len(values) == 1:
        return f"{median:,.1f}"
    q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return f"{median:,.1f} [{q1:,.1f}–{q3:,.1f}]"


def paired_times(missions, pairs):
    per_seed = []
    paired = 0
    for base, comparator in pairs:
        if base not in missions or comparator not in missions:
            continue
        before, after = missions[base], missions[comparator]
        differences = [
            float(other["actual_seconds"]) - float(first["actual_seconds"])
            for key, first in before.items()
            if (other := after.get(key)) and first["actual_seconds"] and other["actual_seconds"]
        ]
        if differences:
            per_seed.append(statistics.median(differences))
            paired += len(differences)
    return f"{summary(per_seed)} ({paired} matched)"


def main(paths):
    runs, missions, revision = read_benchmarks(paths)
    counts = Counter(key[0] for key in runs)
    print("# GeoPulse benchmark results\n")
    print(f"Engine revision: `{revision}`. Executed {len(runs)} runs across {len(counts)} fixtures.")
    print("Values are seed-level medians and interquartile ranges. A single seed has no IQR. These outcomes are simulated.\n")
    print("| Fixture | Runs | Ordinary-only references |")
    print("| --- | ---: | ---: |")
    for fixture, count in sorted(counts.items()):
        refs = sum(key[0] == fixture and key[2] == "reference" for key in runs)
        print(f"| {fixture} | {count} | {refs} |")
    print("\n| Fixture | Horizon | Priority | Seeds | On time / late / unfinished / rejected | Completed journey (s) | Civilian delay (veh-s) |")
    print("| --- | --- | --- | ---: | --- | ---: | ---: |")
    for fixture in sorted(counts):
        for horizon in ("0", "2", "all", "reference"):
            for priority in ("false", "true"):
                matching = [key for key in runs if key[0] == fixture and key[2:] == (horizon, priority)]
                if not matching:
                    continue
                outcomes = Counter(m["status"] for key in matching for m in missions[key].values())
                counts_text = " / ".join(str(outcomes[name]) for name in ("ON_TIME", "LATE", "UNFINISHED", "REJECTED"))
                times = [[float(m["actual_seconds"]) for m in missions[key].values() if m["actual_seconds"]] for key in matching]
                delay = [sum(float(runs[key][f"{period}_{component}"]) for period in ("eval", "followup")
                             for component in ("boundary", "junction", "running")) for key in matching]
                print(f"| {fixture} | {horizon} | {priority} | {len(matching)} | {counts_text} | "
                      f"{summary(statistics.median(seed) for seed in times if seed)} | {summary(delay)} |")
    print("\n## Paired impacts")
    print("\n| Fixture | Horizon | Priority on − off journey (s) | Hybrid − historical journey (s), same priority |")
    print("| --- | --- | --- | --- |")
    for fixture in sorted(counts):
        for horizon in ("0", "2", "all"):
            pairs = [(key, (*key[:3], "true")) for key in runs if key[0] == fixture and key[2:] == (horizon, "false")]
            if not pairs:
                continue
            hybrid = [(key, (*key[:2], "2", key[3])) for key in runs if key[0] == fixture and key[2] == "0"]
            hybrid_result = "—"
            if horizon == "2":
                hybrid_result = "off " + paired_times(missions, (pair for pair in hybrid if pair[0][3] == "false"))
                hybrid_result += ", on " + paired_times(missions, (pair for pair in hybrid if pair[0][3] == "true"))
            print(f"| {fixture} | {horizon} | {paired_times(missions, pairs)} | {hybrid_result} |")
    print("\n| Fixture | Horizon | Priority delay delta (veh-s) | Recovery observed | Recovery (s) | Enabled backlog at recovery (veh-eq) |")
    print("| --- | --- | ---: | --- | ---: | ---: |")
    for fixture in sorted(counts):
        for horizon in ("0", "2", "all"):
            candidates = [run for key, run in runs.items() if key[0] == fixture and key[2:] == (horizon, "true")]
            if not candidates:
                continue
            recovered = [run for run in candidates if run["recovery_seconds"]]
            print(f"| {fixture} | {horizon} | {summary(float(run['signed_priority_delay']) for run in candidates if run['signed_priority_delay'])} | "
                  f"{len(recovered)}/{len(candidates)} | {summary(float(run['recovery_seconds']) for run in recovered)} | "
                  f"{summary(float(run['backlog_at_recovery']) for run in recovered)} |")
    scale = [run for key, run in runs.items() if key[0] == "SCALE" and key[2] != "reference"]
    if scale:
        print(f"\nScale setup: 10×10, 30 ambulances. Evaluation wall time was {summary(float(run['elapsed_ms']) for run in scale)} ms. "
              f"Junction forecasts per run were {summary(float(run['junction_forecasts']) for run in scale)}. "
              "Wall time depends on the machine and concurrent workload.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
