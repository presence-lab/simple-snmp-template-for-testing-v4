# Auto-track mirror — instructor setup

This directory contains scripts and a workflow that copy each student's
auto-track ref (the AI-interaction process trace) into a single
instructor-owned mirror repo on a schedule, and emit a markdown digest
flagging student submissions that warrant a closer look.

## What this gets you

- An authoritative copy of every student's auto-track history, namespaced
  per student. If a student deletes their repo or force-pushes their
  auto-track branch (which the per-repo Ruleset should also block), the
  mirror retains what it last fetched.
- A markdown digest after every cron run that lists students by category:
  `never_tracked`, `code_jump`, `silent`, `fetch_failed`, `push_rejected`.
  These are SOFT signals — students worth a closer look, not students to
  penalize. Flags are designed to be false-positive-tolerant.

## Setup (one-time per assignment)

1. **Create a new private repo** owned by your instructor account or a
   shared TA account. Call it something like `snmp-2026-mirror`. This is
   where the mirrored data accumulates. Don't reuse a student-facing repo.

2. **Create a Personal Access Token** (or a GitHub App installation token)
   with these scopes:
   - `repo` (read access to private student repos in the classroom org)
   - `repo` (write access to your mirror repo)

   Personal tokens work for first deployment; for production, use a GitHub
   App because tokens rotate automatically.

3. **In your mirror repo, set Actions secrets and variables:**
   - Secret `CLASSROOM_TOKEN` — the PAT from step 2
   - Variable `CLASSROOM_ORG` — your classroom org (e.g., `clemson-cpsc-3600`)
   - Variable `ASSIGNMENT_PREFIX` — repo-name prefix shared by all student
     repos for this assignment (e.g., `assignment-snmp-2026`)
   - Variable `MIRROR_REMOTE` — clone URL of this mirror repo
     (e.g., `https://github.com/your-name/snmp-2026-mirror.git`)

4. **Copy the three files into the mirror repo:**
   - `mirror.sh` → `instructor-tools/cron-mirror/mirror.sh`
   - `anomaly_report.py` → `instructor-tools/cron-mirror/anomaly_report.py`
   - `workflow.yml` → `.github/workflows/mirror.yml`

5. **Commit, push, and trigger the workflow** manually once
   (Actions tab → Mirror student auto-track refs → Run workflow).

## What the digest tells you

After each run, the mirror repo's Actions tab shows a workflow run with:

- A "Generate anomaly digest" step whose summary is the markdown report.
- An artifact `mirror-digest-N` containing `per-student.jsonl` and
  `report.md` for offline analysis.

Read the report. Most flagged students will have ordinary explanations
(low push frequency, late starters, etc.). Investigate the ones whose
flags accumulate over multiple digests, especially `code_jump` combined
with `never_tracked` or `silent`.

## What this does NOT do

- It does NOT auto-penalize students or auto-create issues. The digest
  is informational. You decide what action to take.
- It does NOT prevent cheating. It collects evidence; you investigate
  patterns. The Ruleset on the student repo's `auto-track` branch is
  what prevents the simplest tampering attacks.
- It does NOT detect students using non-codex AI tools (ChatGPT in a
  browser, Cursor, etc.). For that, the signal is `never_tracked` or
  `code_jump` — code progresses without proportional AI traces.

## Tuning

- Cron schedule lives in `workflow.yml`. Hourly is reasonable for active
  weeks of an assignment; daily may suffice once submissions stabilize.
- Anomaly thresholds are constants at the top of `anomaly_report.py`:
  `STALENESS_HOURS` and `CODE_JUMP_RATIO`. Adjust per course.
- For very large classes (>500 students), you may want to shard the
  mirror across multiple repos to stay under GitHub's recommended 5GB
  per-repo size. The script doesn't do this automatically.

## Troubleshooting

- **No students appear in the digest:** check that `ASSIGNMENT_PREFIX`
  matches the actual repo names in your classroom org. The prefix is
  whatever GitHub Classroom prepends to student usernames when it
  creates repos from a template.
- **Many `fetch_failed` flags:** the token may not have access to all
  student repos. Verify the token's repo permissions and the org
  membership of the token's owner.
- **Many `push_rejected` flags after the first run:** force-push attacks
  by students. Confirm your Ruleset on the student repos is blocking
  force-pushes to `auto-track`. The mirror retains the original state
  regardless.
