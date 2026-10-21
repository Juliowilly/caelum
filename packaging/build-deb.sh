#!/usr/bin/env bash
# Build dist/caelum_<version>_all.deb from the source tree.
# Needs only dpkg-deb (no debhelper). Usage: packaging/build-deb.sh  (or: make deb)
set -euo pipefail
umask 022

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(python3 -c "import sys; sys.path.insert(0, '$ROOT'); import caelum; print(caelum.__version__)")"
APP_ID="io.github.juliowilly.Caelum"
PKG="caelum_${VERSION}_all"
STAGE="$ROOT/build/deb/$PKG"
PYDIR="$STAGE/usr/lib/python3/dist-packages"

rm -rf "$STAGE"
mkdir -p "$PYDIR" "$STAGE/DEBIAN" "$STAGE/usr/bin" \
         "$STAGE/usr/share/applications" "$STAGE/usr/share/metainfo" \
         "$STAGE/usr/share/icons/hicolor/scalable/apps" "$STAGE/usr/share/doc/caelum"

# Python package — sources only, no bytecode (postinst compiles it)
(cd "$ROOT" && find caelum -name '*.py' -not -path 'caelum/kivy_ui/*' -print0 | xargs -0 -I{} install -D -m 644 {} "$PYDIR/{}")

cat > "$STAGE/usr/bin/caelum" <<'EOF'
#!/usr/bin/python3
from caelum.gtk_ui.app import main
main()
EOF
chmod 755 "$STAGE/usr/bin/caelum"

install -m 644 "$ROOT/data/$APP_ID.desktop"      "$STAGE/usr/share/applications/"
install -m 644 "$ROOT/data/$APP_ID.metainfo.xml" "$STAGE/usr/share/metainfo/"
install -m 644 "$ROOT/data/$APP_ID.svg"          "$STAGE/usr/share/icons/hicolor/scalable/apps/"
install -m 644 "$ROOT/README.md"                 "$STAGE/usr/share/doc/caelum/"
{
    echo "Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/"
    echo "Upstream-Name: caelum"
    echo "Source: https://github.com/Juliowilly/caelum"
    echo
    echo "Files: *"
    echo "License: MIT"
    sed 's/^$/./; s/^/ /' "$ROOT/LICENSE"
} > "$STAGE/usr/share/doc/caelum/copyright"

cat > "$STAGE/DEBIAN/control" <<EOF
Package: caelum
Version: $VERSION
Section: science
Priority: optional
Architecture: all
Depends: python3 (>= 3.8), python3-gi, python3-gi-cairo, gir1.2-gtk-3.0
Suggests: python3-serial, python3-dbus, iio-sensor-proxy
Installed-Size: $(du -sk --exclude=DEBIAN "$STAGE" | cut -f1)
Maintainer: Juliowilly <carlostoscani1@gmail.com>
Homepage: https://github.com/Juliowilly/caelum
Description: live sky overlay for the Linux desktop
 Caelum turns the desktop background into a live sky showing the real
 position of the sun, moon, planets and stars for your location, with
 clouds, rain and snow from live weather data (Open-Meteo, MET Norway).
EOF

cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = configure ]; then
    py3compile -p caelum 2>/dev/null || true
fi
EOF
cat > "$STAGE/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
py3clean -p caelum 2>/dev/null || true
EOF
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/prerm"

mkdir -p "$ROOT/dist"
dpkg-deb --root-owner-group --build "$STAGE" "$ROOT/dist/$PKG.deb"
echo "Built dist/$PKG.deb"
