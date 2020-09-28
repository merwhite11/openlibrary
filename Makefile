#
# Makefile to build css and js files, compile i18n messages and stamp
# version information
#

BUILD=static/build
ACCESS_LOG_FORMAT='%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s"'
GITHUB_EDITOR_WIDTH=127
FLAKE_EXCLUDE=./.*,scripts/20*,vendor/*,node_modules/*
COMPONENTS_DIR=openlibrary/components

# Use python from local env if it exists or else default to python in the path.
PYTHON=$(if $(wildcard env),env/bin/python,python)

.PHONY: all clean distclean git css js components i18n lint

all: git css js components i18n

css: static/css/page-*.less
	mkdir --parents $(BUILD)
	for asset in $^; do \
		echo "Compressing $$asset"; \
	    npx lessc $$asset $(BUILD)/$$(basename $$asset .less).css --clean-css="--s1 --advanced --compatibility=ie8"; \
	done

js:
	mkdir --parents $(BUILD)
	rm -f $(BUILD)/*.js $(BUILD)/*.js.map
	npm run build-assets:webpack
	# This adds FSF licensing for AGPLv3 to our js (for librejs)
	for js in $(BUILD)/*.js; do \
		echo "// @license magnet:?xt=urn:btih:0b31508aeb0634b347b8270c7bee4d411b5d4109&dn=agpl-3.0.txt AGPL-v3.0" | cat - $$js > /tmp/js && mv /tmp/js $$js; \
		echo "\n// @license-end"  >> $$js; \
	done

components: $(COMPONENTS_DIR)/*.vue
	mkdir --parents $(BUILD)
	rm -rf $(BUILD)/components
	# FIXME: Should not inline vue, and should not be in development mode!
	for component in $^; do \
		echo $$component; \
		npx vue-cli-service build --mode development --no-clean --dest $(BUILD)/components --inline-vue --target wc --name "ol-$$(basename $$component .vue)" "$$component"; \
	done

i18n:
	$(PYTHON) ./scripts/i18n-messages compile

git:	
#Do not run these on DockerHub since it recursively clones all the repos before build initiates
ifneq ($(DOCKER_HUB),TRUE)
	git submodule init
	git submodule sync
	git submodule update
endif

clean:
	rm -rf $(BUILD)

distclean:
	git clean -fdx
	git submodule foreach git clean -fdx

load_sample_data:
	@echo "loading sample docs from openlibrary.org website"
	$(PYTHON) scripts/copydocs.py --list /people/anand/lists/OL1815L
	curl http://localhost:8080/_dev/process_ebooks # hack to show books in returncart

reindex-solr:
	psql --host db openlibrary -t -c 'select key from thing' | sed 's/ *//' | grep '^/books/' | PYTHONPATH=$(PWD) xargs python openlibrary/solr/update_work.py -s http://web/ -c conf/openlibrary.yml --data-provider=legacy
	psql --host db openlibrary -t -c 'select key from thing' | sed 's/ *//' | grep '^/authors/' | PYTHONPATH=$(PWD) xargs python openlibrary/solr/update_work.py -s http://web/ -c conf/openlibrary.yml --data-provider=legacy

lint-diff:
	git diff master -U0 | ./scripts/flake8-diff.sh

lint:
	# stop the build if there are Python syntax errors or undefined names
	$(PYTHON) -m flake8 . --count --exclude=$(FLAKE_EXCLUDE) --select=E9,F63,F7,F82 --show-source --statistics
ifndef CONTINUOUS_INTEGRATION
	# exit-zero treats all errors as warnings, only run this in local dev while fixing issue, not CI as it will never fail.
	$(PYTHON) -m flake8 . --count --exclude=$(FLAKE_EXCLUDE) --exit-zero --max-complexity=10 --max-line-length=$(GITHUB_EDITOR_WIDTH) --statistics
endif

test-css:
	npm run test:css

test-js:
	npm run test:js

test-unit:
	npm run test:unit

test-py:
	pytest . --ignore=tests/integration --ignore=scripts/2011 --ignore=infogami --ignore=vendor

test: 
	npm run test && make test-py
