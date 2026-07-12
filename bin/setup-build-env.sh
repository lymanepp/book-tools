#!/usr/bin/env bash
# Install and verify the tools required by the book publishing pipeline.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tools/bin/build-env-common.sh
source "$SCRIPT_DIR/build-env-common.sh"

as_root() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    echo "ERROR: Need root privileges to run: $*" >&2
    exit 1
  fi
}

install_apt_packages() {
  if [[ "${SKIP_APT_INSTALL:-0}" == "1" || "${GITHUB_ACTIONS:-}" == "true" ]]; then
    echo "Skipping apt package install; handled by workflow or caller."
    return
  fi

  command -v apt-get >/dev/null 2>&1 \
    || { echo "ERROR: Debian/Ubuntu apt-get is required." >&2; exit 1; }

  export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a NEEDRESTART_SUSPEND=1
  mapfile -t packages < <(read_build_apt_packages)
  as_root apt-get update -qq
  as_root apt-get install -y --no-install-recommends "${packages[@]}"
}

install_python_packages() {
  [[ "${SKIP_PIP_INSTALL:-0}" != "1" ]] \
    || { echo "Skipping Python package install; handled by workflow."; return; }

  local command=(python3 -m pip install --upgrade -r "$BUILD_PYTHON_REQUIREMENTS_FILE")
  if [[ "${GITHUB_ACTIONS:-}" == "true" || -n "${VIRTUAL_ENV:-}" ]]; then
    "${command[@]}"
    return
  fi

  if python3 -m pip help install 2>/dev/null | grep -q -- '--break-system-packages'; then
    command+=(--break-system-packages)
  fi
  as_root "${command[@]}"
}

install_typst() {
  local current=""
  command -v typst >/dev/null 2>&1 && current="$(typst --version | awk '{print $2}')"
  if [[ "$current" == "$TYPST_VERSION" ]]; then
    echo "Typst $TYPST_VERSION already installed."
    return
  fi
  [[ -z "$current" ]] || echo "Replacing Typst $current with Typst $TYPST_VERSION."

  case "$(uname -m)" in
    x86_64|amd64) ;;
    *) echo "ERROR: Unsupported architecture: $(uname -m)" >&2; exit 1 ;;
  esac

  local tarball="typst-${TYPST_ARCH}.tar.xz"
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  curl -fsSL "https://github.com/typst/typst/releases/download/v${TYPST_VERSION}/${tarball}" \
    -o "$tmp_dir/$tarball"
  echo "${TYPST_SHA256}  $tmp_dir/$tarball" | sha256sum -c -
  tar -xJf "$tmp_dir/$tarball" -C "$tmp_dir"
  as_root install -m 0755 "$tmp_dir/typst-${TYPST_ARCH}/typst" /usr/local/bin/typst
  rm -rf "$tmp_dir"
  typst --version
}

main() {
  install_apt_packages
  install_python_packages
  install_typst
  command -v fc-cache >/dev/null 2>&1 && fc-cache -f
  command -v git >/dev/null 2>&1 && git config --global --add safe.directory "$PWD" || true
  python3 "$SCRIPT_DIR/check-build-env.py"
}

main "$@"
