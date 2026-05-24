PYTHON ?= .venv/bin/python
PYTHON_SCRIPTS = $(shell "$(PYTHON)" -c 'import sysconfig; print(sysconfig.get_path("scripts"))')

.PHONY: setup test lint smoke

setup:
	python3 -m venv .venv
	$(PYTHON) -m pip install -U pip
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m pip install -e .

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests

lint:
	PYTHONPATH=src $(PYTHON) -m compileall -q src tests scripts

smoke:
	$(PYTHON) scripts/manga_to_epub.py --help >/dev/null
	$(PYTHON) scripts/pdf_to_epub_lossless.py --help >/dev/null
	"$(PYTHON_SCRIPTS)/manga-to-epub" --help >/dev/null
	"$(PYTHON_SCRIPTS)/pdf-to-epub-lossless" --help >/dev/null
	PYTHONPATH=src $(PYTHON) -m manga_pdf_to_epub.cli.pdf_to_epub_lossless --help >/dev/null
