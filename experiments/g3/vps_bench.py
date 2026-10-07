"""CPU, 2 threads: model load, query latency (median of 20) and peak RSS of a query-only process.

    taskset -c 0,1 uv run --all-groups python experiments/g3/vps_bench.py <model> [corpus]
"""
import json, resource, statistics, sys, time
from corpus import DATA
from embedders import load
key = sys.argv[1]; corpus = len(sys.argv) > 2
t0 = time.perf_counter(); embed = load(key, threads=2); load_s = time.perf_counter() - t0
qs = [json.loads(l)["consulta"] for l in (DATA / "queries.jsonl").open()]
lat = []
for q in qs[:20]:
    t = time.perf_counter(); embed([q], True); lat.append((time.perf_counter() - t) * 1000)
out = {"model": key, "load_s": round(load_s, 2), "query_ms_p50": round(statistics.median(lat), 1), "query_ms_max": round(max(lat), 1),
       "query_peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)}
if corpus:
    from corpus import rows, text
    t = time.perf_counter(); embed([text(x) for x in rows()], False); out["corpus_cpu2_s"] = round(time.perf_counter() - t, 1)
    out["corpus_peak_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
print(json.dumps(out))
