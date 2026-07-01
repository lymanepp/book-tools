#!/usr/bin/env bash
# Common build-environment bootstrap for the book publishing pipeline.
#
# Supports the active pipeline:
#   - Typst interior PDFs
#   - WeasyPrint cover PDFs
#   - Pandoc DOCX
#   - Pandoc EPUB
#
# Shared by:
#   - .devcontainer/post-create
#   - .github/workflows/build-books.yml
#
# Intentional omissions:
#   - TeX Live / XeLaTeX
#   - qpdf
#   - poppler-utils
#   - jq
#   - unzip

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tools/bin/build-env-common.sh
source "$SCRIPT_DIR/build-env-common.sh"
CHECK_SCRIPT="$SCRIPT_DIR/check-build-env.py"

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

apt_install() {
  if [[ "${SKIP_APT_INSTALL:-0}" == "1" || "${GITHUB_ACTIONS:-}" == "true" ]]; then
    echo "Skipping apt package install; handled by workflow or caller."
    return
  fi

  if ! command -v apt-get >/dev/null 2>&1; then
    echo "ERROR: setup-build-env.sh currently supports Debian/Ubuntu apt-get environments only." >&2
    exit 1
  fi

  export DEBIAN_FRONTEND=noninteractive
  export NEEDRESTART_MODE=a
  export NEEDRESTART_SUSPEND=1

  as_root apt-get update -qq

  mapfile -t apt_packages < <(read_build_apt_packages)
  as_root apt-get install -y --no-install-recommends "${apt_packages[@]}"
}

pip_supports_break_system_packages() {
  python3 -m pip help install 2>/dev/null | grep -q -- '--break-system-packages'
}

install_python_packages() {
  if [[ "${SKIP_PIP_INSTALL:-0}" == "1" ]]; then
    echo "Skipping Python package install; handled by workflow."
    return
  fi

  # Do NOT install/upgrade pip here.
  #
  # In Debian/Ubuntu system Python environments, pip may be apt-managed. Trying
  # to upgrade pip with pip itself can fail with:
  #   ERROR: Cannot uninstall pip 24.0, RECORD file not found.
  #
  # The book pipeline only needs the packages pinned in requirements-build.txt.
  local pip_flags=()
  if pip_supports_break_system_packages; then
    pip_flags+=(--break-system-packages)
  fi

  if [[ "${GITHUB_ACTIONS:-}" == "true" || -n "${VIRTUAL_ENV:-}" ]]; then
    python3 -m pip install --upgrade -r "$BUILD_PYTHON_REQUIREMENTS_FILE"
  else
    as_root python3 -m pip install "${pip_flags[@]}" --upgrade -r "$BUILD_PYTHON_REQUIREMENTS_FILE"
  fi
}

install_typst() {
  if command -v typst >/dev/null 2>&1; then
    local current
    current="$(typst --version | awk '{print $2}')"
    if [[ "$current" == "$TYPST_VERSION" ]]; then
      echo "Typst $TYPST_VERSION already installed."
      return
    fi
    echo "Replacing Typst $current with Typst $TYPST_VERSION."
  fi

  case "$(uname -m)" in
    x86_64|amd64)
      ;;
    *)
      echo "ERROR: Unsupported architecture for bundled Typst install: $(uname -m)" >&2
      echo "Set TYPST_ARCH and TYPST_SHA256 explicitly if you need another target." >&2
      exit 1
      ;;
  esac

  local tarball="typst-${TYPST_ARCH}.tar.xz"
  local url="https://github.com/typst/typst/releases/download/v${TYPST_VERSION}/${tarball}"
  local tmp_dir
  tmp_dir="$(mktemp -d)"

  curl -fsSL "$url" -o "$tmp_dir/$tarball"
  echo "${TYPST_SHA256}  $tmp_dir/$tarball" | sha256sum -c -
  tar -xJf "$tmp_dir/$tarball" -C "$tmp_dir"
  as_root install -m 0755 "$tmp_dir/typst-${TYPST_ARCH}/typst" /usr/local/bin/typst
  rm -rf "$tmp_dir"

  typst --version
}

configure_fonts() {
  if command -v fc-cache >/dev/null 2>&1; then
    fc-cache -f
  fi
}

configure_git() {
  if command -v git >/dev/null 2>&1; then
    git config --global --add safe.directory "$PWD" || true
  fi
}

main() {
  apt_install
  install_python_packages
  install_typst
  configure_fonts
  configure_git

  if [[ -f "$CHECK_SCRIPT" ]]; then
    python3 "$CHECK_SCRIPT"
  else
    echo "WARNING: Missing build-environment checker: $CHECK_SCRIPT" >&2
  fi
}

main "$@"
