#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'TXT'
Usage:
  tools/bin/release-book.sh <book1|book2> <version> [--yes]

Examples:
  tools/bin/release-book.sh book1 1.0.1
  tools/bin/release-book.sh book2 1.0.0 --yes

What it does:
  - requires the main branch
  - updates main and submodules
  - requires clean parent and tools repositories
  - runs the selected book's full local build
  - creates an annotated tag: <book>-v<version>
  - pushes the tag, triggering the GitHub release workflow

The version must be MAJOR.MINOR.PATCH, such as 1.0.1.
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

case "$BOOK" in
  book1)
    TITLE="What Scripture Says, Volume 1"
    ;;
  book2)
    TITLE="What Scripture Says, Volume 2"
    ;;
  *)
    die "Book must be book1 or book2."
    ;;
esac

[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
  || die "Version must be MAJOR.MINOR.PATCH, such as 1.0.1."

[[ -z "$AUTO_YES" || "$AUTO_YES" == "--yes" ]] \
  || die "Unknown option: $AUTO_YES"

command -v git >/dev/null || die "git is required."
command -v python3 >/dev/null || die "python3 is required."
[[ -x tools/bin/build-book.py ]] || die "Run this from the repository root."

TAG="${BOOK}-v${VERSION}"

current_branch="$(git branch --show-current)"
[[ "$current_branch" == "main" ]] \
  || die "Current branch is '$current_branch'; switch to main first."

echo "Preparing release:"
echo "  Book:    $TITLE"
echo "  Version: $VERSION"
echo "  Tag:     $TAG"

run git pull --ff-only
run git submodule update --init --recursive

[[ -z "$(git status --porcelain)" ]] \
  || die "Parent repository has uncommitted or untracked changes."

[[ -z "$(git -C tools status --porcelain)" ]] \
  || die "The tools submodule has uncommitted or untracked changes."

submodule_status="$(git submodule status --recursive)"
if grep -Eq '^[+-U]' <<<"$submodule_status"; then
  printf '%s\n' "$submodule_status" >&2
  die "A submodule is not at the commit recorded by the parent repository."
fi

run git fetch --tags --force

[[ -z "$(git tag -l "$TAG")" ]] \
  || die "Local tag already exists: $TAG"

[[ -z "$(git ls-remote --tags origin "refs/tags/$TAG")" ]] \
  || die "Remote tag already exists: $TAG"

echo
echo "Running final local build..."
run tools/bin/build-book.py "$BOOK"

echo
echo "Build completed. Inspect the files in dist/ before continuing."
echo "The local build is expected to contain draft metadata."

if [[ "$AUTO_YES" != "--yes" ]]; then
  read -r -p "Create and push release tag '$TAG'? Type RELEASE to continue: " answer
  [[ "$answer" == "RELEASE" ]] || die "Release cancelled."
fi

head_sha="$(git rev-parse HEAD)"
tools_sha="$(git -C tools rev-parse HEAD)"

run git tag -a "$TAG" \
  -m "$TITLE — revision $VERSION"

tag_sha="$(git rev-list -n 1 "$TAG")"
[[ "$tag_sha" == "$head_sha" ]] \
  || die "Tag does not point to the current commit."

echo
echo "Release provenance:"
echo "  Source commit: $head_sha"
echo "  Tools commit:  $tools_sha"

run git push origin "$TAG"

cat <<TXT

Release tag pushed successfully.

GitHub Actions should now run the formal release workflow for:
  $TAG

Next:
  1. Open GitHub Actions and verify the release workflow succeeds.
  2. Inspect the exact assets attached to the GitHub release.
  3. Verify SHA256SUMS before uploading those assets to KDP.
TXT
