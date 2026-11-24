# Running the GeoPulse benchmark

**Decision:** Build the engine from the desired revision and record that revision with the results. The Python launch and report scripts use the standard library. The scale run should run by itself for interpretable wall timing.

```sh
./backend/mvnw -f backend/pom.xml -pl engine package
revision=$(git rev-parse HEAD)
python3 scenarios/run_benchmarks.py core "$revision" /tmp/geopulse-core --workers 4
python3 scenarios/run_benchmarks.py scale "$revision" /tmp/geopulse-scale
python3 scenarios/summarize_benchmarks.py /tmp/geopulse-core/*.tsv /tmp/geopulse-scale/*.tsv > /tmp/geopulse-results.md
```

**Fact:** The `smoke` mode covers the same policies for one seed per fixture. It checks benchmark execution and cannot substitute for the 20-seed comparisons. Each core run uses the same 600-second warm state and precomputed schedule for all six policies and its ordinary-only reference. The paired measurement covers 1,800 seconds of evaluation and 600 seconds of follow-up. Scale uses an identical policy matrix for five seeds.

**Decision:** Calibration seeds `-1201` through `-1203` generate frozen profiles from incident-free ordinary traffic. Evaluation seeds `1000–1019` and scale seeds `2000–2004` vary the external base demand and mission timing. The predictable case adds the same scheduled corridor pulse to calibration and evaluation, with its height determined by each run's seed. Known incident confirmations arrive at predeclared ticks.

**Fact:** Each TSV carries the engine revision, profile fingerprint and seeds, schedule fingerprint, policy, individual mission status and outcomes, delay components, civilian population and backlog, measured queue recovery, and forecast workload. The report summarizes these with seed-level medians and interquartile ranges. Positive priority delay means more civilian delay with priority enabled. A blank recovery field means recovery was not observed or there was no ended grant to measure.

**Fact:** The [completed M5 report](../docs/M5_RESULTS.md) covers 980 core runs and 35 scale runs, including the ordinary-only references. Its [underlying TSV](m5-32147e0.tsv.gz) can be decompressed with `gzip -dk` and supplied directly to the summarizer.
