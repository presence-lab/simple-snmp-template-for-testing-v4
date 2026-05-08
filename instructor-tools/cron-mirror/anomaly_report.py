"""Read per-student.jsonl produced by mirror.sh and emit a human-readable
markdown report of anomalies.

Anomaly categories:
- never_tracked       student has main commits but zero auto-track commits
- code_jump           main grew but no recent auto-track activity to back it up
- silent              main has commits but auto-track ref is stale
- fetch_failed        couldn't fetch from student repo (deletion / permissions)
- push_rejected       force-push attack (Ruleset on student repo SHOULD prevent)

These are SOFT signals -- the report flags students worth a closer look,
not students to penalize. Categorical false positives are expected (e.g.,
a student who pushes infrequently might look "silent"); the categories are
designed to be false-positive-tolerant per the project's design priorities.

Usage:
    python anomaly_report.py per-student.jsonl > report.md
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Iterable


# Threshold knobs. Tuned for a multi-week assignment; adjust per course.
STALENESS_HOURS = 48
CODE_JUMP_RATIO = 5  # main commits per auto-track commit


def parse_jsonl(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def hours_since(iso_ts: str) -> float | None:
    if not iso_ts:
        return None
    try:
        dt = datetime.fromisoformat(iso_ts)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(tz=timezone.utc) - dt).total_seconds() / 3600.0


def classify(row: dict) -> list[str]:
    flags: list[str] = []
    if row.get("fetch") == "failed":
        flags.append("fetch_failed")
    if row.get("push") == "failed":
        flags.append("push_rejected")
    main_n = int(row.get("main_commits", 0) or 0)
    at_n = int(row.get("auto_track_commits", 0) or 0)
    if main_n > 0 and at_n == 0:
        flags.append("never_tracked")
    elif main_n > 1 and at_n > 0 and main_n / max(at_n, 1) >= CODE_JUMP_RATIO:
        flags.append("code_jump")
    main_age = hours_since(row.get("main_last_ts", ""))
    at_age = hours_since(row.get("auto_track_last_ts", ""))
    if main_age is not None and at_age is not None:
        # Main updated recently but auto-track is much older: the student is
        # working but not pushing process tracking.
        if main_age < STALENESS_HOURS and at_age > main_age + STALENESS_HOURS:
            flags.append("silent")
    return flags


FLAG_DESCRIPTIONS = {
    "never_tracked":  "Has code commits but zero auto-track snapshots.",
    "code_jump":      f"main commits >= {CODE_JUMP_RATIO}x auto-track commits.",
    "silent":         f"main pushed within last {STALENESS_HOURS}h, but auto-track is stale.",
    "fetch_failed":   "Mirror could not fetch from this repo (deleted? permissions?).",
    "push_rejected":  "Mirror push rejected -- student's auto-track may have been force-pushed.",
}


def render_markdown(rows: Iterable[dict]) -> str:
    flagged: list[tuple[dict, list[str]]] = []
    clean: list[dict] = []
    for r in rows:
        f = classify(r)
        if f:
            flagged.append((r, f))
        else:
            clean.append(r)

    lines: list[str] = []
    lines.append(f"# Auto-track Mirror Digest")
    lines.append("")
    lines.append(f"_Generated: {datetime.now(tz=timezone.utc).isoformat()}_")
    lines.append("")
    lines.append(f"**Total students mirrored:** {len(clean) + len(flagged)}")
    lines.append(f"**Flagged for review:** {len(flagged)}")
    lines.append("")

    if flagged:
        lines.append("## Flagged students")
        lines.append("")
        lines.append("These are SOFT signals -- worth a closer look, not "
                     "automatic verdicts. Most flags have innocent "
                     "explanations.")
        lines.append("")
        lines.append("| Student | Flags | main commits | auto-track commits | last main | last auto-track |")
        lines.append("|---|---|---|---|---|---|")
        for r, flags in sorted(flagged, key=lambda x: x[0].get("student", "")):
            lines.append(
                f"| `{r.get('student','?')}` "
                f"| {', '.join(flags)} "
                f"| {r.get('main_commits','?')} "
                f"| {r.get('auto_track_commits','?')} "
                f"| {r.get('main_last_ts','—')[:10] or '—'} "
                f"| {r.get('auto_track_last_ts','—')[:10] or '—'} |"
            )
        lines.append("")
        lines.append("### Flag glossary")
        for flag, desc in FLAG_DESCRIPTIONS.items():
            lines.append(f"- **{flag}** — {desc}")
        lines.append("")

    lines.append("## Healthy submissions")
    lines.append("")
    lines.append(f"{len(clean)} students with no flags. Counts:")
    lines.append("")
    lines.append("| Student | main commits | auto-track commits |")
    lines.append("|---|---|---|")
    for r in sorted(clean, key=lambda x: x.get("student", "")):
        lines.append(
            f"| `{r.get('student','?')}` "
            f"| {r.get('main_commits','?')} "
            f"| {r.get('auto_track_commits','?')} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: anomaly_report.py per-student.jsonl", file=sys.stderr)
        return 2
    rows = parse_jsonl(sys.argv[1])
    print(render_markdown(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
