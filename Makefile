.PHONY: help setup up down test build release configure backend-test eval web-test compile run-backend run-web data-evaluation data-minimal data-full train-ml
PYTHON ?= python3
.DEFAULT_GOAL := help

configure:
	$(PYTHON) scripts/product.py configure
setup:
	$(PYTHON) scripts/product.py setup
up:
	$(PYTHON) scripts/product.py up
down:
	$(PYTHON) scripts/product.py down
test:
	$(PYTHON) scripts/product.py test
build:
	$(PYTHON) scripts/product.py build
release:
	$(PYTHON) scripts/package_release.py

help:
	@printf '%s\n' 'make backend-test  - run dependency-free backend unit tests' 'make eval          - run CyberTrust-QA against the local corpus' 'make web-test      - run Node web client tests' 'make compile       - compile-check Python sources' 'make run-backend   - start API (stdlib fallback if FastAPI is absent)' 'make run-web       - start Next.js web client'

backend-test:
	PYTHONPATH=backend python3 -m unittest discover -s backend/tests -v

eval:
	PYTHONPATH=backend python3 scripts/evaluation/evaluate_cybertrust.py

web-test:
	npm test --prefix frontend

compile:
	PYTHONPATH=backend python3 -m compileall -q backend

run-backend:
	PYTHONPATH=backend python3 backend/run.py

run-web:
	npm run dev --prefix frontend

data-evaluation:
	PYTHONPATH=backend python3 scripts/bootstrap_data.py --evaluation

data-minimal:
	PYTHONPATH=backend python3 scripts/bootstrap_data.py --minimal

data-full:
	PYTHONPATH=backend python3 scripts/bootstrap_data.py --full

train-ml:
	PYTHONPATH=backend python3 scripts/train_intent.py
	PYTHONPATH=backend python3 scripts/train_ood.py
	PYTHONPATH=backend python3 scripts/evaluate_models.py
