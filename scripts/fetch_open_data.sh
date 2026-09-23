#!/usr/bin/env bash
# Fetch the two free/keyless data sources that had no fetch script before this: openfootball
# (CC0/public domain match data, https://github.com/openfootball/football.json) and
# martj42/international_results (CC0, https://github.com/martj42/international_results).
# Together with scripts/fetch_footballdata_uk.py, this is everything a fresh `git clone`
# needs to rebuild data/ from scratch and run `python scripts/ingest.py`.
#
# Idempotent: skips a source that's already present unless --force is passed. Safe to
# re-run. Never touches anything outside the target directories it's given.
#
# Usage:
#   scripts/fetch_open_data.sh [--force] [data_dir]
#   data_dir defaults to "data" (repo root's data/ directory) - pass a scratch directory
#   to test this script without touching real, already-populated data.

set -euo pipefail

FORCE=0
DATA_DIR="data"
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    *) DATA_DIR="$arg" ;;
  esac
done

OPENFOOTBALL_DIR="$DATA_DIR/openfootball_raw"
RESULTS_CSV="$DATA_DIR/results.csv"
GOALSCORERS_CSV="$DATA_DIR/goalscorers.csv"

mkdir -p "$DATA_DIR"

# --- openfootball/football.json: season-dir/league-code.json layout, e.g.
# openfootball_raw/2015-16/en.1.json - kickcast_engine/data/openfootball.py expects exactly
# this layout directly under $OPENFOOTBALL_DIR. Downloaded as a tarball (one request) rather
# than per-file (hundreds of season/league combos), since that's what a fresh clone needs.
if [ "$FORCE" -eq 0 ] && [ -f "$OPENFOOTBALL_DIR/2015-16/en.1.json" ]; then
  echo "openfootball: already present at $OPENFOOTBALL_DIR (use --force to refetch), skipping"
else
  echo "openfootball: downloading https://github.com/openfootball/football.json (master)..."
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  curl -sL -o "$tmp/football.json.tar.gz" \
    "https://github.com/openfootball/football.json/archive/refs/heads/master.tar.gz"
  tar -xzf "$tmp/football.json.tar.gz" -C "$tmp"
  extracted="$(find "$tmp" -maxdepth 1 -type d -name 'football.json-*')"
  mkdir -p "$OPENFOOTBALL_DIR"
  # rsync-free copy: clear stale content first so a --force refetch can't leave old+new mixed
  rm -rf "${OPENFOOTBALL_DIR:?}"/*
  cp -r "$extracted"/. "$OPENFOOTBALL_DIR"/
  rm -rf "$tmp"
  trap - EXIT
  n_seasons="$(find "$OPENFOOTBALL_DIR" -maxdepth 1 -type d -regex '.*/20[0-9][0-9]-[0-9][0-9]' | wc -l | tr -d ' ')"
  echo "openfootball: extracted to $OPENFOOTBALL_DIR ($n_seasons season directories)"
fi

# --- martj42/international_results: two flat CSVs at the repo root, expected directly at
# $DATA_DIR/results.csv and $DATA_DIR/goalscorers.csv by kickcast_engine/data/international.py.
BASE="https://raw.githubusercontent.com/martj42/international_results/master"
if [ "$FORCE" -eq 0 ] && [ -s "$RESULTS_CSV" ] && [ -s "$GOALSCORERS_CSV" ]; then
  echo "martj42/international_results: already present ($RESULTS_CSV, $GOALSCORERS_CSV), skipping"
else
  echo "martj42/international_results: downloading results.csv and goalscorers.csv..."
  curl -sL -o "$RESULTS_CSV" "$BASE/results.csv"
  curl -sL -o "$GOALSCORERS_CSV" "$BASE/goalscorers.csv"
  echo "martj42/international_results: $(wc -l < "$RESULTS_CSV" | tr -d ' ') rows in results.csv, " \
       "$(wc -l < "$GOALSCORERS_CSV" | tr -d ' ') rows in goalscorers.csv"
fi

echo "done. Next: python scripts/fetch_footballdata_uk.py && python scripts/ingest.py"
