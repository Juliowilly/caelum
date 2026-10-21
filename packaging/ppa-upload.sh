#!/usr/bin/env bash
# Build signed source packages from the committed tree (HEAD) and upload them to the Launchpad PPA.
#
# Usage: packaging/ppa-upload.sh [--upload] [REVISION]
#   Without --upload it only builds and signs, into build/ppa/ (check them first).
#   REVISION is the per-series rebuild number (default 1); bump it to re-upload the same version.
#
# Each Ubuntu series gets its own version, e.g. 1.1.0-1~ubuntu24.04.1, so the newer release
# always wins on upgrade and every series can be rebuilt independently.
set -euo pipefail
umask 022

PPA="ppa:juliowilly/caelum"
KEY="8ADAFA29057A27BE2DD54CC839C70230203512C3"
SERIES=("noble:24.04" "resolute:26.04")

UPLOAD=0
if [ "${1:-}" = "--upload" ]; then UPLOAD=1; shift; fi
REV="${1:-1}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [ -n "$(git status --porcelain)" ]; then
    echo "Commit your changes first: the PPA is built from HEAD." >&2
    exit 1
fi

DEB_VERSION="$(dpkg-parsechangelog -S Version)"      # e.g. 1.1.0-1
UPSTREAM="${DEB_VERSION%-*}"                           # e.g. 1.1.0
MAINT="$(dpkg-parsechangelog -S Maintainer)"
WORK="$ROOT/build/ppa"
rm -rf "$WORK"
mkdir -p "$WORK"

# One upstream tarball for every series: Launchpad rejects a second, different orig for the same version
git archive --format=tar --prefix="caelum-$UPSTREAM/" HEAD -- . ':!debian' | gzip -n > "$WORK/caelum_$UPSTREAM.orig.tar.gz"

first=1
for entry in "${SERIES[@]}"; do
    series="${entry%%:*}"; release="${entry##*:}"
    version="$DEB_VERSION~ubuntu$release.$REV"
    src="$WORK/$series/caelum-$UPSTREAM"
    mkdir -p "$src"
    git archive --format=tar HEAD | tar -x -C "$src"
    cp "$WORK/caelum_$UPSTREAM.orig.tar.gz" "$WORK/$series/"
    {
        echo "caelum ($version) $series; urgency=medium"
        echo
        echo "  * Build for Ubuntu $release ($series)."
        echo
        echo " -- $MAINT  $(date -R)"
        echo
        cat "$src/debian/changelog"
    } > "$src/debian/changelog.new"
    mv "$src/debian/changelog.new" "$src/debian/changelog"
    # -sa: include the orig tarball (first upload of this version); -sd: reuse it
    if [ "$first" = 1 ]; then orig=-sa; else orig=-sd; fi
    (cd "$src" && debuild -S "$orig" -k"$KEY")
    first=0
done

ls -1 "$WORK"/*/*_source.changes
if [ "$UPLOAD" = 1 ]; then
    for changes in "$WORK"/*/*_source.changes; do
        dput "$PPA" "$changes"
    done
    echo "Uploaded. Build status: https://launchpad.net/~juliowilly/+archive/ubuntu/caelum/+packages"
else
    echo "Built and signed only. Re-run with --upload to send to $PPA."
fi
