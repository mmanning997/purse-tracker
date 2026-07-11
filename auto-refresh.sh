#!/bin/bash
# Weekly auto-refresh: pull fresh eBay resale comps, regenerate data.js, and
# deploy (commit + push) so the live dashboard updates. Scheduled via launchd
# (~/Library/LaunchAgents/com.matt.purse-tracker.refresh.plist) — Wed 03:00.
# Run by hand anytime with: bash auto-refresh.sh
set -euo pipefail

# launchd starts with a bare environment; make sure python3 + git are findable.
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
REPO="/Users/matthewmanning/Scripts/purse-tracker"
cd "$REPO"

echo "===== $(date '+%Y-%m-%d %H:%M:%S') refresh start ====="

# Fetch comps + regenerate data.js. If eBay is unreachable this exits non-zero
# (set -e) and we neither commit nor push — next run tries again.
python3 refresh.py --fetch

# Only deploy if the fetch actually changed the generated data.
if git diff --quiet -- data.js data/history.json; then
  echo "no data changes — nothing to deploy"
else
  git add data.js data/history.json data/bags.json
  git commit -m "Auto-refresh eBay comps $(date +%Y-%m-%d)"
  git push origin main
  echo "deployed."
fi

echo "===== $(date '+%Y-%m-%d %H:%M:%S') refresh done ====="
