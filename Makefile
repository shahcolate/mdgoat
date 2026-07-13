.PHONY: help install test lint build clean self-check

help:
	@echo "make install     editable install"
	@echo "make test        run the test suite"
	@echo "make self-check  mdgoat must pass its own gate"
	@echo "make build       build sdist + wheel into dist/"
	@echo "make clean       remove build artifacts"

install:
	pip install -e .

test:
	python -m unittest discover -s tests -v

self-check:
	mdgoat scan README.md --fail-on high

build: clean
	python -m pip install --upgrade build twine
	python -m build
	twine check dist/*

clean:
	rm -rf build dist *.egg-info mdgoat.egg-info .pytest_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
