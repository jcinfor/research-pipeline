"""Parse the rerun log for prototype-vs-mem0_real disagreements."""
import re
import sys
from collections import defaultdict
from pathlib import Path

LOG = Path(r"C:\Users\j_che\AppData\Local\Temp\locomo_rerun.log")

# Match: '  [system_name] qid (cat=N) sub=X judge=Y (Tms): prediction-text'
LINE_RE = re.compile(
    r"^\s*\[(\w+)\]\s+([^\s]+)\s+\(cat=(\d)\)\s+sub=([✓✗])\s+judge=([✓✗])\s+\((\d+)ms\):\s*(.*)$"
)


def main():
    text = LOG.read_text(encoding="utf-8", errors="replace")
    # qid -> system -> {sub, judge, prediction, cat}
    table: dict[str, dict[str, dict]] = defaultdict(dict)
    for line in text.splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue
        sys_name, qid, cat, sub, judge, _ms, pred = m.groups()
        table[qid][sys_name] = {
            "cat": int(cat),
            "sub": sub == "✓",
            "judge": judge == "✓",
            "pred": pred.strip(),
        }

    # Need both prototype AND mem0_real for disagreement
    prototype_fail_mem0_win: list[tuple[str, dict]] = []
    prototype_win_mem0_fail: list[tuple[str, dict]] = []
    both_fail: list[tuple[str, dict]] = []
    both_win: list[tuple[str, dict]] = []

    for qid, by_sys in table.items():
        p = by_sys.get("prototype")
        m = by_sys.get("mem0_real")
        if not (p and m):
            continue
        if not p["judge"] and m["judge"]:
            prototype_fail_mem0_win.append((qid, by_sys))
        elif p["judge"] and not m["judge"]:
            prototype_win_mem0_fail.append((qid, by_sys))
        elif p["judge"] and m["judge"]:
            both_win.append((qid, by_sys))
        else:
            both_fail.append((qid, by_sys))

    print("=" * 70)
    print(f"Q's where BOTH have judge result: "
          f"{len(prototype_fail_mem0_win) + len(prototype_win_mem0_fail) + len(both_win) + len(both_fail)}")
    print("=" * 70)
    print(f"  prototype FAIL & mem0_real WIN:  {len(prototype_fail_mem0_win)}")
    print(f"  prototype WIN  & mem0_real FAIL: {len(prototype_win_mem0_fail)}")
    print(f"  both win:                        {len(both_win)}")
    print(f"  both fail:                       {len(both_fail)}")

    # Category breakdown of disagreements
    print("\n--- Category breakdown: prototype FAIL & mem0_real WIN ---")
    by_cat = defaultdict(int)
    for qid, sysd in prototype_fail_mem0_win:
        by_cat[sysd["prototype"]["cat"]] += 1
    for c in sorted(by_cat):
        print(f"  cat {c}: {by_cat[c]}")

    print("\n--- Category breakdown: prototype WIN & mem0_real FAIL ---")
    by_cat = defaultdict(int)
    for qid, sysd in prototype_win_mem0_fail:
        by_cat[sysd["prototype"]["cat"]] += 1
    for c in sorted(by_cat):
        print(f"  cat {c}: {by_cat[c]}")

    # Print first 12 examples of mem0_real-win cases
    print("\n--- Examples: prototype FAIL, mem0_real WIN (first 12) ---")
    for qid, sysd in prototype_fail_mem0_win[:12]:
        c = sysd["prototype"]["cat"]
        print(f"\n[{qid}] cat={c}")
        print(f"  prototype:  {sysd['prototype']['pred'][:120]}")
        print(f"  mem0_real:  {sysd['mem0_real']['pred'][:120]}")

    # Print prototype-win cases too
    print("\n--- Examples: prototype WIN, mem0_real FAIL (all) ---")
    for qid, sysd in prototype_win_mem0_fail[:12]:
        c = sysd["prototype"]["cat"]
        print(f"\n[{qid}] cat={c}")
        print(f"  prototype:  {sysd['prototype']['pred'][:120]}")
        print(f"  mem0_real:  {sysd['mem0_real']['pred'][:120]}")


if __name__ == "__main__":
    main()
