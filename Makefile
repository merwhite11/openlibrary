#
# Makefile to build css and js files, compile i18n messages and stamp
# version information
#

BUILD=static/build
ACCESS_LOG_FORMAT='%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s"'
GITHUB_EDITOR_WIDTH=127
FLAKE_EXCLUDE=./.*,scripts/20*,vendor/*,node_modules/*

define lessc
	echo Compressing $(1).less; \
	npx lessc static/css/$(1).less $(BUILD)/$(1).css --clean-css="--s1 --advanced --compatibility=ie8"
endef

# Use python from local env if it exists or else default to python in the path.
PYTHON=$(if $(wildcard env),env/bin/python,python)

.PHONY: all clean distclean git css js i18n lint

all: git css js i18n

css:
	mkdir -p $(BUILD)
	for asset in admin book edit form home lists plain subject user book-widget design dev; do \
		$(call lessc,page-$$asset); \
	done

js:
	mkdir -p $(BUILD)
	rm -f $(BUILD)/*.js $(BUILD)/*.js.map
	npm run build-assets:webpack
	# This adds FSF licensing for AGPLv3 to our js (for librejs)
	for js in $(BUILD)/*.js; do \
		echo "// @license magnet:?xt=urn:btih:0b31508aeb0634b347b8270c7bee4d411b5d4109&dn=agpl-3.0.txt AGPL-v3.0" | cat - $$js > /tmp/js && mv /tmp/js $$js; \
		echo "\n// @license-end"  >> $$js; \
	done

i18n:
	$(PYTHON) ./scripts/i18n-messages compile

git:
	git submodule init
	git submodule sync
	git submodule update

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
	su postgres -c "psql openlibrary -t -c 'select key from thing' | sed 's/ *//' | grep '^/books/' | PYTHONPATH=$(PWD) xargs python openlibrary/solr/update_work.py -s http://0.0.0.0/ -c conf/openlibrary.yml --data-provider=legacy"
	su postgres -c "psql openlibrary -t -c 'select key from thing' | sed 's/ *//' | grep '^/authors/' | PYTHONPATH=$(PWD) xargs python openlibrary/solr/update_work.py -s http://0.0.0.0/ -c conf/openlibrary.yml --data-provider=legacy"

lint-diff:
	git diff master -U0 | ./scripts/flake8-diff.sh

lint:
	# stop the build if there are Python syntax errors or undefined names
	$(PYTHON) -m flake8 . --count --exclude=$(FLAKE_EXCLUDE) --select=E9,F63,F7,F82 --show-source --statistics
ifndef CONTINUOUS_INTEGRATION
	# exit-zero treats all errors as warnings, only run this in local dev while fixing issue, not CI as it will never fail.
	$(PYTHON) -m flake8 . --count --exclude=$(FLAKE_EXCLUDE) --exit-zero --max-complexity=10 --max-line-length=$(GITHUB_EDITOR_WIDTH) --statistics
endif

test:
	npm test
	pytest openlibrary/tests openlibrary/mocks openlibrary/olbase openlibrary/plugins openlibrary/utils openlibrary/catalog openlibrary/coverstore scripts/tests
