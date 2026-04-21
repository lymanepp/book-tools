#!/usr/bin/env bash
set -euo pipefail

INPLACE=0

if [[ "${1:-}" == "-i" ]]; then
  INPLACE=1
  shift
fi

# sed script (UTF-8 safe, no dash normalization)
read -r -d '' SED_SCRIPT <<'EOF'
s/[“”„‟]/"/g
s/[‘’‚‛]/'/g
s/ / /g
s/[​‌‍]//g
s/[′]/'/g
s/[″]/"/g
EOF

run_sed() {
  sed -e "$SED_SCRIPT"
}

# Case 1: No files → STDIN → STDOUT
if [[ $# -eq 0 ]]; then
  if [[ $INPLACE -eq 1 ]]; then
    echo "Error: -i cannot be used with stdin" >&2
    exit 1
  fi
  run_sed
  exit 0
fi

# Case 2: Files provided
if [[ $INPLACE -eq 1 ]]; then
  # In-place editing for multiple files
  for f in "$@"; do
    sed -i -e "$SED_SCRIPT" "$f"
  done
else
  # Stream all files to stdout
  run_sed "$@"
fi
