#!/usr/bin/env bash
# Build dist/caelum_<version>_all.deb from debian/ (the same packaging Launchpad builds for the PPA).
# Needs: devscripts debhelper dh-python pybuild-plugin-pyproject python3-all python3-setuptools
# Usage: packaging/build-deb.sh  (or: make deb)
set -euo pipefail
umask 022

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(dpkg-parsechangelog -l "$ROOT/debian/changelog" -S Version)"
WORK="$ROOT/build/deb"
SRC="$WORK/caelum-${VERSION%-*}"

# dpkg-buildpackage writes next to the source dir, so build in a copy of the tree
# (tracked + new files, minus anything .gitignore'd)
rm -rf "$WORK"
mkdir -p "$SRC" "$ROOT/dist"
(cd "$ROOT" && git ls-files -z --cached --others --exclude-standard) |
    (cd "$ROOT" && rsync -a --from0 --files-from=- ./ "$SRC/")

(cd "$SRC" && dpkg-buildpackage -b -us -uc)
mv "$WORK"/caelum_*_all.deb "$ROOT/dist/"
echo "Built dist/caelum_${VERSION}_all.deb"
