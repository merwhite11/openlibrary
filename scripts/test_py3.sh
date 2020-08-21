#!/bin/sh

pytest . \
       --ignore=openlibrary/catalog/marc/tests/test_get_subjects.py \
       --ignore=openlibrary/catalog/marc/tests/test_parse.py \
       --ignore=openlibrary/tests/catalog/test_get_ia.py \
       --ignore=tests/integration \
       --ignore=scripts/2011 \
       --ignore=infogami \
       --ignore=vendor
RETURN_CODE=$?
       
pytest --show-capture=all -v openlibrary/catalog/marc/tests/test_get_subjects.py || true  # internetarchive/openlibrary#3584
pytest --show-capture=all -v openlibrary/catalog/marc/tests/test_parse.py || true  # internetarchive/openlibrary#3584
pytest --show-capture=all -v openlibrary/tests/catalog/test_get_ia.py || true  # internetarchive/openlibrary#3584
flake8 --exit-zero --count --select=E722,F403 --show-source --statistics  # Show bare exceptions and wildcard (*) imports
safety check || true  # Show any insecure dependencies

exit ${RETURN_CODE}
