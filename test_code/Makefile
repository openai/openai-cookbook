.PHONY: clean clean-build clean-pyc clean-test coverage dist docs help install lint lint/flake8 lint/black
.DEFAULT_GOAL := help

define BROWSER_PYSCRIPT
import os, webbrowser, sys

from urllib.request import pathname2url

webbrowser.open("file://" + pathname2url(os.path.abspath(sys.argv[1])))
endef
export BROWSER_PYSCRIPT

define PRINT_HELP_PYSCRIPT
import re, sys

for line in sys.stdin:
	match = re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)
	if match:
		target, help = match.groups()
		print("%-20s %s" % (target, help))
endef
export PRINT_HELP_PYSCRIPT

BROWSER := python -c "$$BROWSER_PYSCRIPT"

help:
	@python -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

clean: clean-build clean-pyc clean-test ## removes all build, test, coverage and Python artifacts

clean-build: ## removes build artifacts
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -f {} +

clean-pyc: ## removes Python file artifacts
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-test: ## removes test and coverage artifacts
	rm -fr .tox/
	rm -f .coverage
	rm -fr htmlcov/
	rm -fr .pytest_cache

lint/autopep8: ## check style with flake8
	autopep8 data_quality_package tests --diff -r

lint/black: ## check style with black
	black --check data_quality_package tests

lint/isort: ## check style with isort
	isort --check --diff data_quality_package/ tests/

lint: lint/isort lint/autopep8 lint/black  ## check style

format/autopep8: ## format style with autopep8
	autopep8 data_quality_package tests -r --in-place

format/black: ## format style with black
	black data_quality_package tests

format/isort: ## format style with isort
	isort data_quality_package tests

format: format/autopep8 format/isort format/black ## format style

test:
	python3 -m run tests/ --abc=hi --env_file_path=hihi --cfg_file_path=hihihi
test-docker: ## run tests quickly with the default Python
	bash ./util/docker_test.sh

test-all-docker: ## run tests on every Python version with tox
	bash ./util/docker_tox.sh

coverage: ## check code coverage quickly with the default Python
	coverage run --source data_quality_package -m pytest
	coverage report -m
	coverage html
	$(BROWSER) htmlcov/index.html
coverage-docker:
	bash ./util/docker_coverage.sh
Security: ## checks for security in dependencies and current package
	safety check -i 39462 -i 40291
	bandit -r data_quality_package/

docs: ## generates Sphinx documentation using doc_type, including API docs.
#	rm -f -r docs/_build
#	rm -f -r docs
#	rm -f docs/src/data_quality_package.rst
#	rm -f docs/src/modules.rst
#	sphinx-apidoc -f -o docs/src/ data_quality_package
	$(MAKE) -C docs clean
#	rm docs/src/data_quality_package/modules.rst
	rm -f docs/src/data_quality_package/{modules,data_quality_package*}.rst
	sphinx-apidoc -f -o docs/src/data_quality_package data_quality_package --ext-githubpages --ext-viewcode
#	$(MAKE) -C docs html
	$(MAKE) -C docs $(doc_type)
#	$(BROWSER) docs/_build/html/index.html
##	mv docs/$(doc_type) .
##	rm -r docs
##	mv $(doc_type) docs
#	touch docs/.nojekyll

servedocs: docs ## compile the docs watching for changes. Usage:  use it whenever you have a server that wants to update as soon as the file changes. The command should be always running.
	watchmedo shell-command -p '*.rst;*.md' -c '$(MAKE) -C docs $(doc_type)' -R -D .

#release: dist #glue_zip lambda_zip ## package and upload a release
#	twine upload dist/*
bump: ## bumps the version given argument version, which can be patch, minor or major.
	bumpversion $(version) --allow-dirty
dist: clean ## builds source and wheel package, version can be patch, minor or major.
	# sudo apt-get install gcc libpq-dev -y #uncomment if it is first time
	# sudo apt-get install python-dev  python-pip -y
	# sudo apt-get install python3-dev python3-pip python3-venv python3-wheel -y
	# pip3 install wheel
	python3 setup.py sdist
	python3 setup.py bdist_wheel
	python3 setup.py sdist bdist_wheel
	ls -l dist

install: clean ## install the package to the active Python's site-packages
	python3 setup.py install
pause: ##pause for 10 seconds
	sleep 1
#done: test pause test-all pause security pause docs doc_type=html lint release
done: test pause test-all pause security pause docs doc_type=html lint #release
# format

glue_zip: dist ## creates a lambda zip file from the glue_requirements.txt and current data_quality_package version.
	mkdir -p wheel_dir/python
	find dist -name "*.whl" -print0 | xargs -0 -I {} cp {} wheel_dir/python
	pip wheel --wheel-dir=wheel_dir/python -r glue_requirements.txt
	for z in wheel_dir/python/*.whl; do unzip $$z -d wheel_dir/python; done
	cd wheel_dir/python; rm -r -f numpy* pandas* boto* aiohttp* setuptools* pytz* yarl* frozenlist* dateutil* urllib3* multidict* certifi* s3transfer* idna* requests attrs* certifi* pymysql* pyarrow* packaging* jmespath* idna* frozenlist* async_timeout* aiosignal* six.py
	find wheel_dir/python -type f -iname "*.whl" -exec rm -rf {} +
	cd wheel_dir/python/; zip glue_zip * -r
	mv wheel_dir/python/glue_zip.zip dist/glue_zip.zip
	find wheel_dir/python -type d -iname "*" -exec rm -rf {} +
	rm -r -f wheel_dir

lambda_zip:  ## creates a lambda zip file from the lambda_requirements.txt and current data_quality_package version.
	mkdir -p wheel_dir/python
	sudo find . -name "*.pyc" -exec chmod +x {} \;
	find dist -name "*.whl" -print0 | xargs -0 -I {} cp {} wheel_dir/python
	pip wheel --wheel-dir=wheel_dir/python -r requirements.txt
	for z in wheel_dir/python/*.whl; do unzip $$z -d wheel_dir/python; done
	find wheel_dir/python -type f -iname "*.whl" -exec rm -rf {} +
	cd wheel_dir/python; rm -r -f boto3 botocore certifi chardet pkg_resources charset_normalizer jmespath-0.10.0.data idna jmespath dateutil requests s3transfer setuptools six urllib3
	cd wheel_dir/python; rm six.py 
	cd wheel_dir/; zip lambda_layer * -r
	mv wheel_dir/lambda_layer.zip lambda_layer.zip
	find wheel_dir/python -type d -iname "*" -exec rm -rf {} +
	rm -r -f wheel_dir
current_branch=$(shell git rev-parse --abbrev-ref HEAD)
github_pages:	## the make file command to create documentation from current branch branch.
	
	make docs doc_type=html
	cd docs/build/html; touch .nojekyll
	git switch documentation
	git ls-files --exclude-standard | grep -v -E "$(git -C . rev-parse --sq-quote --show-toplevel)/.gitignore" | xargs -r rm -rf --
	find . -type d -not -path "*/\.*" -empty -delete
	mv -t . docs/build/html/*
	rm -rf docs
	echo "check the current changes, if suitable push it to origin/documentation. and then switch to $(current_branch)"
