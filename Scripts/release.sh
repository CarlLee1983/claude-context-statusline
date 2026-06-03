#!/usr/bin/env bash
# 發版：打 tag、算 tarball sha256、把 packaging/homebrew/Formula 的範本填入版本與 sha
# 後寫進 homebrew-tap repo 並推送。
# Cut a release: tag, compute the tag tarball's sha256, render the formula templates
# into the homebrew-tap repo, and push.
#
# 用法 / Usage:  Scripts/release.sh <version>        # 例：Scripts/release.sh 0.2.0
# tap 位置覆寫 / override tap location:  HOMEBREW_TAP_DIR=/path/to/homebrew-tap
# 只試跑不推送 / dry run (no tag/push):  RELEASE_DRY_RUN=1 Scripts/release.sh 0.2.0
set -euo pipefail

VERSION="${1:?usage: Scripts/release.sh <version e.g. 0.2.0>}"
DRY_RUN="${RELEASE_DRY_RUN:-0}"
REPO="CarlLee1983/claude-context-statusline"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$ROOT/packaging/homebrew/Formula"
TAP_DIR="${HOMEBREW_TAP_DIR:-$(dirname "$ROOT")/homebrew-tap}"
TARBALL="https://github.com/$REPO/archive/refs/tags/v$VERSION.tar.gz"

run() { if [ "$DRY_RUN" = "1" ]; then echo "[dry-run] $*"; else "$@"; fi; }

if [ ! -d "$TAP_DIR/Formula" ]; then
  echo "!! tap 不存在 / tap not found: $TAP_DIR" >&2
  echo "   先 clone：git clone https://github.com/CarlLee1983/homebrew-tap \"$TAP_DIR\"" >&2
  exit 1
fi

echo "==> tag v$VERSION"
run git tag "v$VERSION"
run git push origin "v$VERSION"

echo "==> sha256 of $TARBALL"
if [ "$DRY_RUN" = "1" ]; then
  SHA="0000000000000000000000000000000000000000000000000000000000000000"
  echo "    [dry-run] skipping download; using placeholder sha"
else
  SHA="$(curl -fsSL "$TARBALL" | shasum -a 256 | awk '{print $1}')"
  echo "    $SHA"
fi

for f in ctx-statusline ai-usage-monitor swiftbar-ai-usage; do
  sed -e "s|archive/refs/tags/v[0-9][0-9.]*\\.tar\\.gz|archive/refs/tags/v$VERSION.tar.gz|" \
      -e "s|sha256 \"[a-f0-9]*\"|sha256 \"$SHA\"|" \
      "$SRC_DIR/$f.rb" > "$TAP_DIR/Formula/$f.rb"
  echo "    rendered $TAP_DIR/Formula/$f.rb"
done

echo "==> commit & push tap"
run git -C "$TAP_DIR" add Formula
run git -C "$TAP_DIR" commit -m "release: v$VERSION"
run git -C "$TAP_DIR" push
echo "✅ released v$VERSION"
