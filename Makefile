clean:
	find . -name '*.pyc' -delete

requirements:
	pip install -r test_requirements.txt

test:
	tox

.PHONY: clean, requirements
