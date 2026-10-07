"""Peak calls and tokens per calendar minute from the ledger (network misses only)."""
import json, sys, collections
L = [json.loads(l) for l in open("/home/jwhoami/.cache/whoami/ledger.jsonl")]
since = sys.argv[1] if len(sys.argv) > 1 else ""
for model in sorted({x["model"] for x in L}):
    calls, toks = collections.Counter(), collections.Counter()
    for x in L:
        if x["model"] == model and x["cache"] == "miss" and x["ts"] >= since:
            calls[x["ts"][:16]] += 1; toks[x["ts"][:16]] += x["total_tokens"]
    if calls:
        print(model, "peak RPM", max(calls.values()), "peak TPM", max(toks.values()), "calls", sum(calls.values()))
