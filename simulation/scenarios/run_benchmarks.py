"""Run GeoPulse's headless evaluation from the repository root."""
import argparse
import concurrent.futures
import pathlib
import subprocess
import sys


CORE_FIXTURES = ("ORDINARY", "PREDICTABLE", "LOCAL_OBSTRUCTION", "DISTANT_OBSTRUCTION",
                 "RECEIVING_BLOCKED", "CONFLICT", "DISCONNECTED")


def run_job(args, job):
    mode, fixture, seed_interval = job
    name = f"{mode}-{fixture.lower()}-{seed_interval.replace(':', '-')}"
    final = args.output / f"{name}.tsv"
    temporary = final.with_suffix(".tmp")
    command = ["java", "-Xmx384m", "-XX:ActiveProcessorCount=2", "-cp", args.classes,
               "in.geopulse.engine.BenchmarkSuite", mode, args.revision, fixture, seed_interval]
    with temporary.open("w", encoding="utf-8") as stream:
        subprocess.run(command, stdout=stream, check=True)
    temporary.replace(final)
    return final


def jobs_for(mode):
    if mode == "smoke":
        return [(mode, fixture, "1000:1001") for fixture in CORE_FIXTURES] + [(mode, "SCALE", "2000:2001")]
    if mode == "scale":
        return [(mode, "SCALE", "2000:2005")]
    return [(mode, fixture, f"{seed}:{seed+5}") for fixture in CORE_FIXTURES for seed in range(1000, 1020, 5)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("smoke", "core", "scale"))
    parser.add_argument("revision", help="Git revision represented by the compiled engine")
    parser.add_argument("output", type=pathlib.Path)
    parser.add_argument("--classes", default="backend/engine/target/classes")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    args.output.mkdir(parents=True, exist_ok=True)
    jobs = jobs_for(args.mode)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = [pool.submit(run_job, args, job) for job in jobs]
        for completed in concurrent.futures.as_completed(pending):
            print(completed.result(), file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
