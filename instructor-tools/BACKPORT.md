# Backport guide

What needs to move from this development template
(`simple-snmp-template-for-testing-v4`) to live student-facing template
repos and to instructor-side infrastructure when the capture system is
released.

This document is the canonical record of changes; consult it whenever
porting a stable iteration of the capture system to:

- Sibling student template repos (`simple-SNMP-template`,
  `simple-snmp-template-for-testing-v3`, etc., and downstream classroom
  assignment templates)
- Instructor-owned mirror repos (created fresh per assignment cycle)
- The GitHub Classroom org's settings (Rulesets, secrets, variables)

---

## 1. Design priorities (read first)

Before porting any change, internalize the priorities that drove it.
These constrain which changes are mandatory vs. optional and how they
should be configured for student-facing deployments:

1. **Never interfere with student code or cause progress loss.** Hard
   constraint. Snapshots must remain isolated to the local
   `refs/auto-track/snapshots` ref and the remote
   `refs/heads/auto-track` branch; nothing in the pipeline ever touches
   `refs/heads/main`, the working tree, or `.git/index`.
2. **Assume students don't understand git** and won't read messages
   outside the explicit test results. No banner, error, or stderr hint
   counts as "the student was warned."
3. **Assume multi-machine work is normal** and pushes WILL get out of
   sync. Build for it, don't fight it.
4. **Prefer false negatives over false positives.** A savvy student
   exploiting a hole is acceptable; a legitimate student looking like a
   cheater is not.
5. **Detection lives on the instructor side.** The local snapshot
   machinery is best-effort plumbing; the cron mirror is the
   load-bearing detection layer.

If a future change conflicts with one of these, escalate the design
question rather than porting silently.

---

## 2. Files that changed in the student template

These all live in the student-facing template and must be ported to any
sibling student template repo. After porting all of them, regenerate
`tools/INTEGRITY_HASHES.txt` per the section at the bottom.

| File | Nature of change | Why | Port priority |
|---|---|---|---|
| `.codex/hooks/_run.py` | Added `SNAPSHOT_SUPPRESSED_HOOKS = {"pre_tool_use", "session_start"}` and a one-line env-var set in `main()` so those two hooks don't fire atexit-snapshots. | Reduces snapshot volume ~40-50% during heavy codex sessions. PreToolUse / SessionStart events are still recorded in the JSONL streams; their commits are folded into the next non-suppressed snapshot. | Required |
| `tests/_capture/sitecustomize_payload.py` | Added `if _should_skip(): return` at the top of `_trigger_snapshot()`. | Covers the edge case where a student activates the venv before launching codex (no `_run.py` re-exec, env var arrives after `sitecustomize` was imported). Without this, the suppression silently fails for those students. | Required |
| `tests/_capture/orchestrator.py` | Added `force: bool = False` parameter to `take_snapshot`. When `True`, bypasses tree-SHA dedupe but keeps session-id dedupe. | Lets `run_tests.py` always log a result, even when the tracked tree is unchanged from the previous snapshot. Critical for instructor visibility into "student ran tests N times today." | Required |
| `tests/_capture/capture.py` | Added matching `force` parameter to `session_finish`, forwarded to `take_snapshot`. | Plumbing for the orchestrator change above. | Required |
| `tests/conftest.py` | `pytest_sessionfinish` reads `CAPTURE_FORCE_SNAPSHOT` env var and passes `force=...` to `session_finish`. | The env-var bridge so the inner pytest invoked by `run_tests.py` honors the flag. | Required |
| `run_tests.py` | Sets `CAPTURE_FORCE_SNAPSHOT=1` in the inner pytest env (`_subprocess_env()`), and passes `force=True` on the outer wrapper's `session_finish` call. | Wires `run_tests.py` invocations to always-record. | Required |
| `tools/verify_integrity.py` | Added `AGENTS.md` and `AI_POLICY.md` to the `TRACKED` list. | Detects accidental or deliberate modification of these instruction documents. | Required |
| `tests/_capture/git_ops.py` | (a) `push_auto_track_background` pushes the local `refs/auto-track/snapshots` ref to remote `refs/heads/auto-track`. (b) `fetch_auto_track` reads the remote `refs/heads/auto-track` branch into the local origin-tip cache. (c) `pick_first_parent` silently auto-recovers from true divergence: resets local to origin and logs the dropped commits. | (a) + (b) The local ref name is preserved for backward compatibility with audit and orchestrator code paths, but the remote canonical ref is now the protectable branch only. There is no longer a hidden custom ref on the remote. (c) Removes the "stuck pushing forever" failure mode that hits multi-machine students who don't understand git. | Required |
| `tests/test_capture_git_ops.py` | `test_pick_first_parent_divergence_*` updated to assert auto-recovery. | The old test asserted "local wins on divergence." After the recovery change, that assertion is wrong. | Required |
| `tests/_capture/auth.py` | Rewrote the `"rejected"` hint message: confirms code is safe, clarifies the issue is process-tracking only, tells students to contact the instructor rather than suggesting `git pull --rebase` (which is wrong for auto-track refs). | Old hint was misleading and asked students to do git they don't understand. With auto-recovery in place, students should rarely see this; if they do, contacting the instructor is the right action. | Required |
| `.github/workflows/integrity.yml` | (a) Removed `pull_request` trigger. (b) Added `continue-on-error: true` to the verify step. (c) Added a `::warning::` annotation on violation, no longer fails the workflow. (d) Uploads `integrity.out` as a 30-day artifact. | Stops red CI badges from showing on student PRs/commits when they accidentally edit a pinned file. The signal is preserved as workflow annotation + artifact for instructor tooling. | Required |
| `tools/INTEGRITY_HASHES.txt` | Regenerated to reflect new file contents. | Hashes change with code. | Regenerate per repo (do not copy verbatim) |
| `PROCESS_TRACKING.md` | Reconciled the student-facing doc with the single-ref simplification: leads with both local ref and remote branch, shows how to inspect either, notes the `auto-track` branch is visibly in the branch list (expected, not a leak), and adds an integrity-note line about the org Ruleset's protection. | The old wording said the trail was "not visible from a normal `git log`" — true locally, but the branch DOES appear in GitHub's UI. Without the update, students who notice the branch could think the system is misbehaving and try to delete it. | Required (student-facing) |

### Per-repo regeneration of integrity hashes

After porting all the above to a target repo, run from that repo's root:

```bash
python tools/verify_integrity.py --update
python tools/verify_integrity.py    # confirms "OK - 36 capture files unchanged."
```

The hashes are content-dependent and per-line-ending-normalized, so they
are NOT portable across repos that have any whitespace differences. Always
regenerate after porting.

---

## 3. Files that go to instructor-side infrastructure ONLY

These live under `instructor-tools/cron-mirror/` in this dev template but
are NOT part of the student-facing template. **Do not port them to
student template repos.** They go to a separate instructor-owned mirror
repo, one per assignment cycle.

| File | Destination in mirror repo |
|---|---|
| `instructor-tools/cron-mirror/mirror.sh` | `instructor-tools/cron-mirror/mirror.sh` (or any path you prefer, just match the workflow's path). |
| `instructor-tools/cron-mirror/anomaly_report.py` | `instructor-tools/cron-mirror/anomaly_report.py`. |
| `instructor-tools/cron-mirror/workflow.yml` | `.github/workflows/mirror.yml`. |
| `instructor-tools/cron-mirror/README.md` | `instructor-tools/cron-mirror/README.md` for future-you to remember the setup. |

See `instructor-tools/cron-mirror/README.md` for the full setup
runbook (token creation, secret/variable names, etc.).

---

## 4. GitHub UI configuration (NOT in code)

These configurations live in GitHub's web UI and must be applied per
classroom org / per mirror repo. They cannot be committed to a repo.

### 4.1 Org-level Ruleset on the student template's `auto-track` branch

Where: classroom org → Settings → Rules → Rulesets → New branch ruleset.

| Setting | Value |
|---|---|
| Name | `Protect auto-track history` |
| Enforcement status | Active |
| Target repositories | "All repositories" or pattern match the assignment prefix (e.g., `assignment-snmp-2026-*`) |
| Target branches (by pattern) | `auto-track` |
| Bypass list | Empty (no bypasses) |
| Block force pushes | ✅ |
| Restrict deletions | ✅ |
| Other rules | Leave OFF (no required reviews, no required status checks, no required signed commits) |

Apply once per classroom org. Inherits to all existing AND newly-created
repos in the org that match the target pattern.

### 4.2 Instructor mirror repo (one per assignment cycle)

Create a new private repo owned by the instructor account or a shared
TA account. Suggested naming: `<course>-<term>-mirror` (e.g.,
`cpsc3600-spring2026-mirror`).

In that repo's Settings → Secrets and variables → Actions:

| Type | Name | Value |
|---|---|---|
| Secret | `CLASSROOM_TOKEN` | PAT or GitHub App installation token with: read access to all student repos in the classroom org, write access to this mirror repo. |
| Variable | `CLASSROOM_ORG` | The classroom org name (e.g., `clemson-cpsc-3600`). |
| Variable | `ASSIGNMENT_PREFIX` | The student-repo name prefix for this assignment (e.g., `assignment-snmp-2026`). |
| Variable | `MIRROR_REMOTE` | Clone URL of THIS mirror repo (e.g., `https://github.com/cpsc3600/cpsc3600-spring2026-mirror.git`). |

### 4.3 Token setup

For first deployment, a Personal Access Token (Classic) works. Required
scopes:

- `repo` (full read access to private student repos via the classroom org)

For ongoing production use, a GitHub App is preferred — installation
tokens rotate automatically, scoped permissions are explicit, and the
audit trail is cleaner. App permissions needed:

- Repository: Contents (read) on student repos
- Repository: Contents (write) on mirror repo
- Subscribed event: `push` (only if also doing webhook-based mirroring;
  not needed for cron-only)

---

## 5. Deployment order

Apply in this order to avoid breaking running assignment cycles:

### 5.1 First, in each student template repo

1. Port all files in §2.
2. Regenerate `tools/INTEGRITY_HASHES.txt` per the instructions in §2.
3. Commit and push.
4. Spot-check by running `python run_tests.py` from a clean checkout
   and confirming a snapshot lands on `refs/heads/auto-track`.
5. From a student-perspective test repo, attempt
   `git push origin <something>:refs/heads/auto-track --force` —
   confirm it's rejected if you've already applied the Ruleset.

### 5.2 Then, in the GitHub Classroom org

6. Create the org-level Ruleset per §4.1.

### 5.3 Then, the instructor mirror

7. Create the mirror repo per §4.2.
8. Drop in the three files from §3.
9. Configure secrets and variables per §4.2.
10. Trigger the mirror workflow manually once (Actions tab → Run workflow).
11. Verify the digest in the workflow run summary matches expectations.

### 5.4 Finally, monitor

12. After a week of student activity, review the digest. Tune
    `STALENESS_HOURS` and `CODE_JUMP_RATIO` in `anomaly_report.py` if
    the false-positive rate is uncomfortable.

---

## 6. Verification checklist

After deployment, confirm each of these works on a test student repo:

- [ ] `python run_tests.py` produces a snapshot on `refs/heads/auto-track` even when source code is unchanged from the previous run (force=True path).
- [ ] Codex hook firing produces snapshots on PostToolUse, PermissionRequest, UserPromptSubmit, Stop — but NOT on PreToolUse or SessionStart.
- [ ] Editing `AGENTS.md` triggers the integrity workflow but does NOT fail the workflow run (annotation only, status check stays green).
- [ ] `git push origin <commit>:refs/heads/auto-track --force` is rejected by GitHub.
- [ ] Auto-track snapshots appear on `refs/heads/auto-track` on origin (the only remote ref the system maintains; the local ref name `refs/auto-track/snapshots` is internal and not pushed).
- [ ] Mirror workflow runs end-to-end and produces a digest that lists the test repo correctly.
- [ ] Manufacturing a divergent local auto-track ref (then running pytest) produces a `divergence-recovered` line in `.test-runs.log` and resets the local ref to origin without surfacing anything to the student.

---

## 7. Rollback

If a backported change causes a regression:

- **Code change:** revert the offending file from the previous-known-good
  commit on the target repo. `tools/verify_integrity.py --update` will
  pick up the new (reverted) hash.
- **Ruleset:** disable the ruleset (Settings → Rules → Rulesets → Disable).
  Existing student work is unaffected; the ref is no longer protected.
- **Mirror workflow:** disable the workflow in the mirror repo
  (Actions → Mirror student auto-track refs → Disable workflow). Already-
  mirrored data is preserved; new student pushes simply aren't ingested
  until you re-enable.

The capture system as a whole has a global off-switch:
`project-template-config.json` → `"capture_enabled": false`. If a
backport breaks something catastrophically, flip that to false in the
student template, push, and capture goes silent across all student
repos at their next pytest invocation.

---

## 8. Known gaps and pending work

Things this dev template can address in future iterations, listed here
so they don't get forgotten:

- **Webhook-based mirror (real-time)** as an alternative to cron. The
  cron mirror has a multi-hour blind spot during which a force-push
  attack could complete unmirrored if the Ruleset were bypassed.
  Requires a small server (Cloud Run / Lambda / Fly.io). Not implemented.
- **Per-student grading dashboard.** The mirror produces a markdown
  digest; a richer dashboard with charts of activity-over-time per
  student would help during grading sweeps. Not implemented.
- **Automatic anomaly notifications** (Slack / email) when flags exceed
  thresholds. Currently the digest is read manually from the workflow
  run summary. Not implemented.
- **Detection of non-codex AI tools.** ChatGPT-in-browser, Cursor, and
  Claude-in-browser don't fire codex hooks. The signal for these is
  `never_tracked` or `code_jump` from the mirror. There is no
  client-side detection planned (and arguably none is feasible).
- **Improved `auth.py` hint coverage.** Other rare push-failure modes
  (DNS resolution issues, GitHub outage) still fall through to generic
  text. Cosmetic.

---

## 9. Per-iteration release log

Date the relevant entries when pushing a stable iteration to live
student repos.

| Date | Iteration summary | Ported to |
|---|---|---|
| _(YYYY-MM-DD)_ | Initial release of the v4-developed capture system: dual-ref push, Ruleset-protectable auto-track branch, silent divergence recovery, force-snapshot for run_tests.py, suppressed pre-tool-use/session-start hooks, AGENTS.md/AI_POLICY.md integrity-pinned, de-saliened CI, instructor cron mirror. | _(list target repos)_ |
| 2026-05-08 | First sibling-repo propagation of the v4 capture iteration: dual-ref push, silent divergence recovery, `force=True` snapshot for `run_tests.py`, suppressed pre-tool-use/session-start atexit snapshots, `AGENTS.md` + `AI_POLICY.md` pinned, integrity workflow desalienced (continue-on-error + `::warning::` + artifact). 147/147 capture tests pass in each target. Commits not yet pushed to remotes. Org-level Ruleset and instructor mirror NOT yet applied. | `python-class-project-starter` (commit `dc9b126`), `simple-SNMP-template` (commit `8a534fa`), `simple-SNMP-reference-implementation` (commit `b45402d`) |
| 2026-05-08 | Follow-up simplification: dropped the redundant remote `refs/auto-track/snapshots` ref. Push and fetch now use only `refs/heads/auto-track`. Local ref name unchanged. Two refs were never useful once the branch became protectable — students could already see the branch in GitHub's UI. 147/147 capture tests still pass. | `python-class-project-starter` (commit `7384c15`), `simple-SNMP-template` (commit `f3c8cbf`), `simple-SNMP-reference-implementation` (commit `c907d97`) |
| 2026-05-08 | Student-facing doc fix to match the single-ref world: `PROCESS_TRACKING.md` now names both the local ref and the remote `auto-track` branch, shows how to inspect either, and the integrity note mentions the org-level Ruleset protection on the branch. Plus `python-class-project-starter` gained an `INSTRUCTOR_SETUP.md` runbook for the org Ruleset. | `python-class-project-starter` (commits `1048fd2`, `f867134`), `simple-SNMP-template` (commit `39fb635`), `simple-SNMP-reference-implementation` (commit `70c31e4`) |
