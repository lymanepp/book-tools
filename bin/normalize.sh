#!/usr/bin/env bash
set -euo pipefail

in_place=false
if [[ "${1:-}" == "-i" ]]; then
  in_place=true
  shift
fi

sed_args=(
  -e 's/[“”„‟]/"/g'
  -e "s/[‘’‚‛]/'/g"
  -e 's/\([0-9]\)-\([0-9]\)/\1–\2/g'
  -e 's/\([0-9]\)—\([0-9]\)/\1–\2/g'
  -e 's/ — /—/g'
  -e 's/\.\.\./…/g'
  -e 's/ / /g'
  -e 's/[​‌‍]//g'
  -e "s/′/'/g"
  -e 's/″/"/g'
)

if $in_place; then
  (($#)) || { echo 'ERROR: -i cannot be used with stdin.' >&2; exit 2; }
  sed -i "${sed_args[@]}" "$@"
else
  sed "${sed_args[@]}" "$@"
fi
