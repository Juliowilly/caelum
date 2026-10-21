.PHONY: run test deb snap flatpak wheel clean

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

wheel:
	python3 -m pip wheel --no-deps --no-build-isolation -w dist .

clean:
	rm -rf build dist build-dir .flatpak-builder *.egg-info *.snap
