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

TYPST_VERSION="${TYPST_VERSION:-0.14.2}"
TYPST_ARCH="${TYPST_ARCH:-x86_64-unknown-linux-musl}"
TYPST_SHA256="${TYPST_SHA256:-a6044cbad2a954deb921167e257e120ac0a16b20339ec01121194ff9d394996d}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "ERROR: setup-build-env.sh currently supports Debian/Ubuntu apt-get environments only." >&2
    exit 1
  fi

  export DEBIAN_FRONTEND=noninteractive
  export NEEDRESTART_MODE=a
  export NEEDRESTART_SUSPEND=1

  as_root apt-get update -qq

  as_root apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    fontconfig \
    fonts-ebgaramond \
    fonts-texgyre \
    git \
    pandoc \
    python3 \
    python3-pip \
    xz-utils \
    libcairo2 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libharfbuzz0b \
    libharfbuzz-subset0 \
    shared-mime-info
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
  # On GitHub Actions ubuntu-24.04, pip is installed by Debian/Ubuntu as an apt
  # package. Trying to upgrade it with pip causes:
  #   ERROR: Cannot uninstall pip 24.0, RECORD file not found.
  #
  # The book pipeline only needs these Python packages.
  local pip_flags=()
  if pip_supports_break_system_packages; then
    pip_flags+=(--break-system-packages)
  fi

  as_root python3 -m pip install "${pip_flags[@]}" --upgrade \
    python-docx \
    pypdf \
    weasyprint
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
