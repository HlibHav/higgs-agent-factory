#!/usr/bin/env bash
# Opens the upstream IHBench PR from the HlibHav fork. Run only on Glib's explicit word.
set -euo pipefail

if [ "${I_AM_GLIB_AND_SAID_PUSH_TO_BOSON:-}" != "yes" ]; then
  echo "Refusing: set I_AM_GLIB_AND_SAID_PUSH_TO_BOSON=yes to open the PR to boson-ai/ihbench." >&2
  exit 1
fi

FORK=/Users/Glebazzz/Claude/PROJECTS/ihbench-higgs
BRANCH=feat/higgs-realtime-client

# Pre-flight: the fork's remote branch must be exactly the local branch.
git -C "$FORK" fetch origin
local_sha=$(git -C "$FORK" rev-parse "refs/heads/$BRANCH")
remote_sha=$(git -C "$FORK" rev-parse "refs/remotes/origin/$BRANCH")
if [ "$local_sha" != "$remote_sha" ]; then
  echo "Abort: origin/$BRANCH ($remote_sha) != local $BRANCH ($local_sha). Push or reconcile first." >&2
  exit 1
fi

gh pr create --repo boson-ai/ihbench --base main --head HlibHav:feat/higgs-realtime-client --title "Add Higgs Realtime client (higgs-realtime backend)" --body-file "$(dirname "$0")/PR_BODY.md"
