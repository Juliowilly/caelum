.PHONY: run test deb snap flatpak flatpak-bundle wheel clean

run:
	python3 -m caelum

test:
	python3 -m unittest discover -s tests

deb:
	packaging/build-deb.sh

snap:
	snapcraft pack

flatpak:
	flatpak run org.flatpak.Builder --user --install --force-clean --disable-rofiles-fuse \
		build-dir flatpak/io.github.juliowilly.Caelum.yml

# Single-file bundle for GitHub Releases; installing it pulls the GNOME runtime from Flathub
flatpak-bundle:
	flatpak run org.flatpak.Builder --user --force-clean --disable-rofiles-fuse \
		--repo=build/flatpak-repo build-dir flatpak/io.github.juliowilly.Caelum.yml
	mkdir -p dist
	flatpak build-bundle --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo \
		build/flatpak-repo dist/caelum-$$(python3 -c 'import caelum; print(caelum.__version__)').flatpak \
		io.github.juliowilly.Caelum master

wheel:
	python3 -m pip wheel --no-deps --no-build-isolation -w dist .

clean:
	rm -rf build dist build-dir .flatpak-builder *.egg-info *.snap
