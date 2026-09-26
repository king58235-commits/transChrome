"""Timing/merge summary of backend logs (live logs/*.log or replay logs).

For each translation unit: time from the last Japanese final it contains to
the Chinese line being ready, whether the Japanese line had already moved on
to the next sentence (a newer partial or final) by then, and whether the unit
merged several STT finals.

Usage (from backend/):
    venv\\Scripts\\python.exe benchmark\\analyze_session_log.py <log> [<log> ...] [--units]
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import datetime as dt
import re
from collections import Counter


def parse(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    ts = lambda l: dt.datetime.strptime(l[:23], "%Y-%m-%d %H:%M:%S,%f")
    events, units = [], {}
    for i, line in enumerate(lines):
        if "[PARTIAL JA]" in line:
            events.append((ts(line), "partial", None))
        elif m := re.search(r"\[FINAL JA #(\d+)\]", line):
            events.append((ts(line), "final", int(m.group(1))))
        elif m := re.search(r"\[TRANSLATION BUFFER #(\d+)\]", line):
            segs = [int(x) for x in re.search(r"segments=\[([\d, ]+)\]", lines[i + 1]).group(1).split(",")]
            text = lines[i + 2].removeprefix("text=")
            reason = re.search(r"reason=(\w+)", lines[i + 3]).group(1)
            units[int(m.group(1))] = {"segs": segs, "ja": text, "reason": reason}
        elif m := re.search(r"\[ZH-TW #(\d+)\]", line):
            u = int(m.group(1))
            events.append((ts(line), "zh", u))
            if u in units:
                units[u]["zh"] = lines[i + 1]
    return events, units


def summarize(path, show_units):
    events, units = parse(path)
    final_t = {e[2]: e[0] for e in events if e[1] == "final"}
    delays, behind = [], 0
    for t, kind, u in events:
        if kind != "zh" or u not in units or units[u]["segs"][-1] not in final_t:
            continue
        ft = final_t[units[u]["segs"][-1]]
        delays.append((t - ft).total_seconds())
        if any(k in ("partial", "final") and ft < tt < t for tt, k, _ in events):
            behind += 1
    delays.sort()
    n = len(delays)
    merged = sum(len(v["segs"]) > 1 for v in units.values())
    print(f"\n== {path}")
    print(f"STT finals: {len(final_t)}  translation units: {len(units)}  merged units: {merged}")
    print(f"flush reasons: {dict(Counter(v['reason'] for v in units.values()))}")
    if n:
        print(f"JA final -> ZH ready: avg {sum(delays)/n:.2f}s  median {delays[n//2]:.2f}s  p90 {delays[int(n*0.9)]:.2f}s")
        print(f"ZH ready after the JA line already moved to the next sentence: {behind}/{n} ({behind/n:.0%})")
    if show_units:
        for u, v in units.items():
            mark = "+" if len(v["segs"]) > 1 else " "
            print(f"  {mark}#{u} {v['ja']}  ->  {v.get('zh', '')}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--units"]
    for p in args:
        summarize(p, "--units" in sys.argv)
