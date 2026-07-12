#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'TXT'
Usage: tools/bin/release-book.sh <book1|book2> <MAJOR.MINOR.PATCH> [--yes]

Builds the selected book, creates <book>-v<version>, and pushes the tag to
trigger the GitHub release workflow.
TXT
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

run() {
  printf '\n$'
  printf ' %q' "$@"
  printf '\n'
  "$@"
}

[[ $# -ge 2 && $# -le 3 ]] || { usage; exit 2; }

BOOK="$1"
VERSION="$2"
AUTO_YES="${3:-}"
BOOK_ENV="$BOOK/book.env"

[[ "$BOOK" == "book1" || "$BOOK" == "book2" ]] || die "Book must be book1 or book2."
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "Version must be MAJOR.MINOR.PATCH."
[[ -z "$AUTO_YES" || "$AUTO_YES" == "--yes" ]] || die "Unknown option: $AUTO_YES"
[[ -x tools/bin/build-book.py && -f "$BOOK_ENV" ]] || die "Run this from the repository root."

# shellcheck disable=SC1090
source "$BOOK_ENV"
TAG="${BOOK}-v${VERSION}"

[[ "$(git branch --show-current)" == "main" ]] || die "Switch to main before releasing."

printf 'Preparing release:\n  Book:    %s\n  Version: %s\n  Tag:     %s\n' "$BOOK_TITLE" "$VERSION" "$TAG"

run git pull --ff-only
run git submodule update --init --recursive

[[ -z "$(git status --porcelain)" ]] || die "Parent repository has uncommitted or untracked changes."
[[ -z "$(git -C tools status --porcelain)" ]] || die "The tools submodule has uncommitted or untracked changes."

submodule_status="$(git submodule status --recursive)"
if grep -Eq '^[+-U]' <<<"$submodule_status"; then
  printf '%s\n' "$submodule_status" >&2
  die "A submodule is not at the commit recorded by the parent repository."
fi

run git fetch --tags
! git show-ref --verify --quiet "refs/tags/$TAG" || die "Tag already exists: $TAG"

run tools/bin/build-book.py "$BOOK"

echo
echo "Build completed. Inspect dist/ before continuing."
echo "The local build is expected to contain draft metadata."

if [[ "$AUTO_YES" != "--yes" ]]; then
  read -r -p "Create and push release tag '$TAG'? Type RELEASE to continue: " answer
  [[ "$answer" == "RELEASE" ]] || die "Release cancelled."
fi

head_sha="$(git rev-parse HEAD)"
tools_sha="$(git -C tools rev-parse HEAD)"

run git tag -a "$TAG" -m "$BOOK_TITLE — revision $VERSION"

printf '\nRelease provenance:\n  Source commit: %s\n  Tools commit:  %s\n' "$head_sha" "$tools_sha"
run git push origin "$TAG"

cat <<TXT

Release tag pushed successfully: $TAG

Next:
  1. Verify the GitHub release workflow succeeds.
  2. Inspect the assets attached to the release.
  3. Verify SHA256SUMS before uploading to KDP.
TXT
