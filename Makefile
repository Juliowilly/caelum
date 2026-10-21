.PHONY: run deb wheel clean

run:
	python3 -m caelum

deb:
	packaging/build-deb.sh

wheel:
	python3 -m pip wheel --no-deps --no-build-isolation -w dist .

clean:
	rm -rf build dist *.egg-info
