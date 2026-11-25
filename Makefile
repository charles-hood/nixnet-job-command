PYTHON ?= python3
PORT ?= 8742

.PHONY: setup run test check-python clean

setup: check-python
	@./setup.sh

check-python:
	@$(PYTHON) -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' \
		|| (echo "NixNet Job Command needs Python 3.9 or newer." && $(PYTHON) --version && exit 1)
	@$(PYTHON) --version

run: check-python
	@test -f config.toml || test -f config.json || echo "No config.toml yet; using defaults and profile.example.json"
	NJC_PORT=$(PORT) $(PYTHON) app/server.py

test: check-python
	$(PYTHON) -m unittest discover -s tests -v

clean:
	rm -rf data/*.db data/*.db-wal data/*.db-shm data/screenshots __pycache__ app/__pycache__ tests/__pycache__
