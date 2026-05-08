#!/usr/bin/env bash
# Mirror student auto-track refs into an instructor-owned repo.
#
# Usage (called from a GitHub Actions cron workflow on the instructor mirror
# repo, with a PAT or GitHub App installation token in $GH_TOKEN that has
# read access to all student repos in the classroom org and write access to
# the mirror repo):
#
#     ./mirror.sh <classroom-org> <repo-prefix> <mirror-repo-url>
#
# Example:
#     ./mirror.sh clemson-cpsc-3600 assignment-snmp-2026 \
#         https://x-access-token:$GH_TOKEN@github.com/instructor/snmp-mirror.git
#
# For each student repo whose name starts with <repo-prefix>, this:
#   1. Fetches refs/heads/auto-track and refs/heads/main from the student.
#   2. Pushes them into the mirror as
#        refs/students/<student-suffix>/auto-track
#        refs/students/<student-suffix>/main
#      where <student-suffix> is the part of the repo name after the prefix.
#   3. Records counts for the digest step.
#
# Mirror push uses --no-force-fetch semantics: if a student force-pushed
# auto-track between cron runs (which the Ruleset on the student repo should
# prevent, but defense-in-depth), the mirror push fails for that ref and we
# log it as an anomaly. The mirror retains its previously-recorded tip --
# evidence is preserved.
#
# Never deletes refs from the mirror. A student deleting their repo or its
# auto-track branch produces a fetch failure logged as anomaly; the mirror
# keeps whatever was last seen.

set -uo pipefail

ORG="${1:?usage: mirror.sh <org> <prefix> <mirror-url>}"
PREFIX="${2:?usage: mirror.sh <org> <prefix> <mirror-url>}"
MIRROR_URL="${3:?usage: mirror.sh <org> <prefix> <mirror-url>}"

OUT_DIR="${OUT_DIR:-./digest-out}"
mkdir -p "$OUT_DIR"

# Per-run digest gathered into a single JSON Lines file. The Python
# anomaly-detection step reads this and produces the human-readable report.
DIGEST_FILE="$OUT_DIR/per-student.jsonl"
: > "$DIGEST_FILE"

ANOMALY_LOG="$OUT_DIR/anomalies.log"
: > "$ANOMALY_LOG"

mirror_repo_dir="$(mktemp -d -t mirror-repo-XXXXXX)"
git -C "$mirror_repo_dir" init -q --bare

# Configure the mirror remote once.
git -C "$mirror_repo_dir" remote add mirror "$MIRROR_URL"

# Pull existing namespaced refs so we can compare and avoid no-op pushes.
git -C "$mirror_repo_dir" fetch -q mirror "refs/students/*:refs/students/*" || true

list_repos() {
    # Lists clone URLs and names of repos in the org matching the prefix.
    # gh paginates automatically with --paginate.
    gh api -H "Accept: application/vnd.github+json" \
        "orgs/$ORG/repos?per_page=100" --paginate \
        -q ".[] | select(.name | startswith(\"$PREFIX\")) | [.name, .clone_url] | @tsv"
}

mirror_one_student() {
    local repo_name="$1"
    local clone_url="$2"
    local student_suffix="${repo_name#$PREFIX-}"
    [ "$student_suffix" = "$repo_name" ] && student_suffix="$repo_name"

    # Inject the token into the clone URL for fetch.
    local fetch_url="${clone_url/https:\/\//https:\/\/x-access-token:$GH_TOKEN@}"

    # Fetch student's auto-track and main into the mirror's local refs.
    local fetch_status="ok"
    local fetch_err
    if ! fetch_err=$(git -C "$mirror_repo_dir" fetch -q "$fetch_url" \
            "+refs/heads/auto-track:refs/students/$student_suffix/auto-track" \
            "+refs/heads/main:refs/students/$student_suffix/main" 2>&1); then
        fetch_status="failed"
        echo "[fetch-fail] $repo_name: $fetch_err" >> "$ANOMALY_LOG"
    fi

    local at_tip at_count main_tip main_count last_at_ts last_main_ts
    at_tip=$(git -C "$mirror_repo_dir" rev-parse --verify -q \
        "refs/students/$student_suffix/auto-track" 2>/dev/null || echo "none")
    main_tip=$(git -C "$mirror_repo_dir" rev-parse --verify -q \
        "refs/students/$student_suffix/main" 2>/dev/null || echo "none")

    if [ "$at_tip" != "none" ]; then
        at_count=$(git -C "$mirror_repo_dir" rev-list --count "$at_tip" 2>/dev/null || echo 0)
        last_at_ts=$(git -C "$mirror_repo_dir" log -1 --format=%cI "$at_tip" 2>/dev/null || echo "")
    else
        at_count=0
        last_at_ts=""
    fi
    if [ "$main_tip" != "none" ]; then
        main_count=$(git -C "$mirror_repo_dir" rev-list --count "$main_tip" 2>/dev/null || echo 0)
        last_main_ts=$(git -C "$mirror_repo_dir" log -1 --format=%cI "$main_tip" 2>/dev/null || echo "")
    else
        main_count=0
        last_main_ts=""
    fi

    # Push refs into the mirror remote (non-force, so a force-push attack
    # by the student would be visible as a push rejection here).
    local push_status="ok"
    local push_err
    if ! push_err=$(git -C "$mirror_repo_dir" push -q mirror \
            "refs/students/$student_suffix/auto-track" \
            "refs/students/$student_suffix/main" 2>&1); then
        push_status="failed"
        echo "[push-fail] $repo_name: $push_err" >> "$ANOMALY_LOG"
    fi

    # JSONL line for the digest step. Using printf to avoid quoting issues.
    printf '{"repo":"%s","student":"%s","auto_track_tip":"%s","auto_track_commits":%s,"auto_track_last_ts":"%s","main_tip":"%s","main_commits":%s,"main_last_ts":"%s","fetch":"%s","push":"%s"}\n' \
        "$repo_name" "$student_suffix" \
        "$at_tip" "$at_count" "$last_at_ts" \
        "$main_tip" "$main_count" "$last_main_ts" \
        "$fetch_status" "$push_status" \
        >> "$DIGEST_FILE"
}

count=0
while IFS=$'\t' read -r name url; do
    [ -z "$name" ] && continue
    mirror_one_student "$name" "$url"
    count=$((count + 1))
done < <(list_repos)

echo "mirrored $count student repos" | tee -a "$ANOMALY_LOG"
