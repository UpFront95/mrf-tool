#!/usr/bin/env bash
# =============================================================================
# start-web.sh — Launch the mrf-rad web server for the MRF Rate Tool
# =============================================================================
#
# PURPOSE
#   This script is called by the mrf-rad.service systemd unit. It dynamically
#   discovers all payer Parquet directories and starts the FastAPI/uvicorn web
#   server that serves the rate query UI.
#
# HOW IT WORKS
#   1. It finds every directory under PARQUET_BASE that matches *-aba/ (the
#      naming convention for ABA-profile parquet outputs). Each such directory
#      holds .parquet files for one payer (e.g. bsca-aba/, bcbstx-aba/).
#   2. It builds a comma-separated glob string pointing to *.parquet inside
#      each of those directories. This is the format mrf-rad web expects for
#      its PARQUET_GLOB argument.
#   3. It exec's into mrf-rad web, replacing this shell process so systemd
#      tracks the uvicorn PID directly (clean shutdown on SIGTERM).
#
# ADDING A NEW PAYER
#   Drop a new <payer>-aba/ directory of .parquet files under PARQUET_BASE and
#   restart the service: `systemctl --user restart mrf-rad`
#   No edits to this script or the service file are required.
#
# ENVIRONMENT VARIABLES (loaded by systemd from .env before this runs)
#   MRF_USER      HTTP Basic Auth username  (default: aba)
#   MRF_PASS      HTTP Basic Auth password  (default: rates)
#   MRF_WEB_HOST  bind address              (default: 0.0.0.0)
#   MRF_WEB_PORT  port                      (default: 8000)
#
# LOCATION
#   /srv/share/mrf-tool/scripts/start-web.sh
# =============================================================================

set -euo pipefail

# Root directory where per-payer ABA parquet subdirs live.
# Each subdir is named <payer>-aba/ and contains *.parquet files.
PARQUET_BASE="/svr/data/mrf-tool/parquet"

# Full path to the mrf-rad CLI inside the project virtualenv.
MRF_RAD="/srv/share/mrf-tool/.venv/bin/mrf-rad"

# Build a comma-joined list of glob patterns — one per matching payer dir
# that actually contains at least one .parquet file.
# Example result:
#   /svr/data/mrf-tool/parquet/bsca-aba/*.parquet,/svr/data/mrf-tool/parquet/bcbstx-aba/*.parquet
#
# Empty <payer>-aba/ dirs are skipped on purpose: DuckDB's read_parquet
# raises "No files found that match the pattern" if any glob in the list
# matches zero files, which would take down every query. Such empty dirs
# appear transiently while a new payer is mid-parse (the output dir exists
# before the .parquet is written), so we must exclude them here.
PARQUET_GLOB=$(for d in "${PARQUET_BASE}"/*-aba/; do
    compgen -G "${d}*.parquet" >/dev/null 2>&1 && printf '%s*.parquet\n' "${d}"
done | paste -sd,)

if [[ -z "${PARQUET_GLOB}" ]]; then
    echo "ERROR: No *-aba/ directories found under ${PARQUET_BASE}" >&2
    exit 1
fi

echo "Starting mrf-rad web with parquet glob:"
echo "  ${PARQUET_GLOB}"
echo "Binding to ${MRF_WEB_HOST:-0.0.0.0}:${MRF_WEB_PORT:-8000}"

# exec replaces this shell with mrf-rad so systemd tracks the real PID.
# mrf-rad web reads MRF_USER/MRF_PASS/MRF_WEB_HOST/MRF_WEB_PORT from env
# (set by EnvironmentFile in the service unit).
exec "${MRF_RAD}" web "${PARQUET_GLOB}" \
    --host "${MRF_WEB_HOST:-0.0.0.0}" \
    --port "${MRF_WEB_PORT:-8000}"
