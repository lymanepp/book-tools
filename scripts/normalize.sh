#!/usr/bin/env bash
set -euo pipefail

INPLACE=0

if [[ "${1:-}" == "-i" ]]; then
  INPLACE=1
  shift
fi

SED_SCRIPT=$(cat <<'EOF'
s/[“”„‟]/"/g
s/[‘’‚‛]/'/g
s/ — /—/g
s/ / /g
s/[​‌‍]//g
s/′/'/g
s/″/"/g
EOF
)

run_sed() {
  sed -e "$SED_SCRIPT" "$@"
}

if [[ $# -eq 0 ]]; then
  if [[ $INPLACE -eq 1 ]]; then
    echo "Error: -i cannot be used with stdin" >&2
    exit 1
  fi
  run_sed
  exit 0
fi

if [[ $INPLACE -eq 1 ]]; then
  for f in "$@"; do
    sed -i -e "$SED_SCRIPT" "$f"
  done
else
  run_sed "$@"
fi
