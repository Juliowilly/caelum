#!/usr/bin/env bash
# Windows build: run in an MSYS2 UCRT64 shell with the packages the CI workflow installs
# (.github/workflows/windows.yml). Output: dist/caelum/ and dist/caelum-<version>-windows-x64.zip
set -euo pipefail
cd "$(dirname "$0")/../.."

VERSION=$(python -c 'import caelum; print(caelum.__version__)')
rm -rf build/windows dist/caelum
python -m PyInstaller --noconfirm --clean \
    --workpath build/windows --distpath dist packaging/windows/caelum.spec

cp LICENSE dist/caelum/LICENSE.txt
ZIP="caelum-${VERSION}-windows-x64.zip"
(cd dist && rm -f "$ZIP" && zip -qr "$ZIP" caelum)
echo "dist/$ZIP"
