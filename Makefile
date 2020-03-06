.PHONY: clean requirements quality test test-all validate upgrade selfcheck

clean:
	find . -name '__pycache__' -exec rm -rf {} +
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	rm -fr build/
	rm -fr dist/
	rm -fr *.egg-info

requirements: ## install test requirements
	pip install -r requirements/test.txt

quality: ## check coding style with pycodestyle and pylint
	tox -e quality

test: clean ## run tests in the current virtualenv
	pytest

test-all: quality ## run tests on every supported Python/Django combination
	tox

validate: quality pii_check test ## run tests and quality checks

upgrade: export CUSTOM_COMPILE_COMMAND=make upgrade
upgrade: ## update the pip requirements files to use the latest releases satisfying our constraints
	pip install -qr requirements/pip_tools.txt
	pip-compile --rebuild --upgrade -o requirements/pip_tools.txt requirements/pip_tools.in
	pip-compile --rebuild --upgrade -o requirements/base.txt requirements/base.in
	pip-compile --rebuild --upgrade -o requirements/tests.txt requirements/tests.in
	pip-compile --rebuild --upgrade -o requirements/scripts.txt requirements/scripts.in
	pip-compile --rebuild --upgrade -o requirements/quality.txt requirements/quality.in

selfcheck: ## check that the Makefile is well-formed
	@echo "The Makefile is well-formed."
