#!/usr/bin/env bash
# Shared book-build environment configuration.
#
# This file is sourced by both:
#   - tools/bin/setup-build-env.sh
#   - .github/workflows/build-books.yml
#
# Keep version pins and canonical environment file paths here so the GitHub
# workflow does not drift away from the local/devcontainer setup script.

BUILD_ENV_COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_REPO_ROOT="$(cd "$BUILD_ENV_COMMON_DIR/../.." && pwd)"

TYPST_VERSION="${TYPST_VERSION:-0.15.1}"
TYPST_ARCH="${TYPST_ARCH:-x86_64-unknown-linux-musl}"
TYPST_SHA256="${TYPST_SHA256:-a6d077d0a95eed5a2eba715b2dae06be954f624ccbf85758a03f389ded33118c}"

BUILD_PYTHON_VERSION="${BUILD_PYTHON_VERSION:-3.12}"

BUILD_APT_PACKAGES_FILE="${BUILD_APT_PACKAGES_FILE:-$BUILD_REPO_ROOT/tools/build-apt-packages.txt}"
BUILD_PYTHON_REQUIREMENTS_FILE="${BUILD_PYTHON_REQUIREMENTS_FILE:-$BUILD_REPO_ROOT/requirements-build.txt}"

read_build_apt_packages() {
  awk '
    /^[[:space:]]*#/ { next }
    /^[[:space:]]*$/ { next }
    { print $1 }
  ' "$BUILD_APT_PACKAGES_FILE"
}

build_apt_packages_one_line() {
  read_build_apt_packages | paste -sd ' ' -
}
