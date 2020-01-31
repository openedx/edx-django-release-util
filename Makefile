.PHONY: clean requirements upgrade

clean:
	find . -name '*.pyc' -delete

requirements:
	pip install -r requirements/tests.txt

test:
	tox

upgrade: export CUSTOM_COMPILE_COMMAND=make upgrade
upgrade: ## update the pip requirements files to use the latest releases satisfying our constraints
	pip install -qr requirements/pip_tools.txt
	pip-compile --rebuild --upgrade -o requirements/pip_tools.txt requirements/pip_tools.in
	pip-compile --rebuild --upgrade -o requirements/tests.txt requirements/tests.in
	pip-compile --rebuild --upgrade -o requirements/scripts.txt requirements/scripts.in
