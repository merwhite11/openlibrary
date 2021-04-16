"""New script to handle solr updates.

Author: Anand Chitipothu

Changes:
2013-02-25: First version
2018-02-11: Use newer config method
"""
import _init_path

from six.moves import urllib
import logging
import json
import datetime
import time
import web
import sys
import re
import socket

from openlibrary.solr import update_work
from openlibrary.config import load_config
from infogami import config

logger = logging.getLogger("openlibrary.solr-updater")


def read_state_file(path):
    try:
        return open(path).read()
    except IOError:
        logger.error("State file %s is not found. Reading log from the beginning of today", path)
        return datetime.date.today().isoformat() + ":0"

def get_default_offset():
    return datetime.date.today().isoformat() + ":0"


class InfobaseLog:
    def __init__(self, hostname, exclude=None):
        """
        :param str hostname:
        :param str|None exclude: if specified, excludes records that include the string
        """
        self.base_url = 'http://%s/openlibrary.org/log' % hostname
        self.offset = get_default_offset()
        self.exclude = exclude

    def tell(self):
        return self.offset

    def seek(self, offset):
        self.offset = offset.strip()

    def read_records(self, max_fetches=10):
        """Reads all the available log records from the server.
        """
        for i in range(max_fetches):
            url = "%s/%s?limit=100" % (self.base_url, self.offset)
            logger.debug("Reading log from %s", url)
            try:
                jsontext = urllib.request.urlopen(url).read()
            except urllib.error.URLError as e:
                logger.error("Failed to open URL %s", url, exc_info=True)
                if e.args and e.args[0].args == (111, 'Connection refused'):
                    logger.error('make sure infogami server is working, connection refused from %s', url)
                    sys.exit(1)
                raise

            try:
                d = json.loads(jsontext)
            except:
                logger.error("Bad JSON: %s", jsontext)
                raise
            data = d['data']
            # no more data is available
            if not data:
                logger.debug("no more records found")
                # There's an infobase bug where we'll sometimes get 0 items, but the
                # binary offset will have incremented...?
                if 'offset' in d:
                    # There's _another_ infobase bug where if you query a future date,
                    # it'll return back 2020-12-01. To avoid solrupdater getting stuck
                    # in a loop, only update the offset if it's newer than the current
                    old_day, old_boffset = self.offset.split(':')
                    old_boffset = int(old_boffset)
                    new_day, new_boffset = d['offset'].split(':')
                    new_boffset = int(new_boffset)
                    if new_day >= old_day and new_boffset >= old_boffset:
                        self.offset = d['offset']
                return

            for record in data:
                if self.exclude and self.exclude in json.dumps(record):
                    continue
                yield record

            self.offset = d['offset']


def parse_log(records, load_ia_scans: bool):
    for rec in records:
        action = rec.get('action')
        if action == 'save':
            key = rec['data'].get('key')
            if key:
                yield key
        elif action == 'save_many':
            changes = rec['data'].get('changeset', {}).get('changes', [])
            for c in changes:
                yield c['key']

        elif action == 'store.put':
            # A sample record looks like this:
            # {
            #   "action": "store.put",
            #   "timestamp": "2011-12-01T00:00:44.241604",
            #   "data": {
            #       "data": {"borrowed": "false", "_key": "ebooks/books/OL5854888M", "_rev": "975708", "type": "ebook", "book_key": "/books/OL5854888M"},
            #       "key": "ebooks/books/OL5854888M"
            #   },
            #   "site": "openlibrary.org"
            # }
            data = rec.get('data', {}).get("data", {})
            key = data.get("_key", "")
            if data.get("type") == "ebook" and key.startswith("ebooks/books/"):
                edition_key = data.get('book_key')
                if edition_key:
                    yield edition_key
            elif (load_ia_scans and data.get("type") == "ia-scan" and
                  key.startswith("ia-scan/")):
                identifier = data.get('identifier')
                if identifier and is_allowed_itemid(identifier):
                    yield "/books/ia:" + identifier

            # Hack to force updating something from admin interface
            # The admin interface writes the keys to update to a document named
            # 'solr-force-update' in the store and whatever keys are written to that
            # are picked by this script
            elif key == 'solr-force-update':
                keys = data.get('keys')
                for k in keys:
                    yield k

        elif action == 'store.delete':
            key = rec.get("data", {}).get("key")
            # An ia-scan key is deleted when that book is deleted/darked from IA.
            # Delete it from OL solr by updating that key
            if key.startswith("ia-scan/"):
                ol_key = "/works/ia:" + key.split("/")[-1]
                yield ol_key

def is_allowed_itemid(identifier):
    if not re.match("^[a-zA-Z0-9_.-]*$", identifier):
        return False

    # items starts with these prefixes are not books. Ignore them.
    ignore_prefixes = config.get("ia_ignore_prefixes", [])
    for prefix in ignore_prefixes:
        if identifier.startswith(prefix):
            return False

    return True

def update_keys(keys):
    if not keys:
        return 0

    # FIXME: Some kind of hack introduced to work around DB connectivity issue
    global args
    logger.debug("Args: %s" % str(args))
    update_work.load_configs(args.ol_url, args.config, 'default')

    keys = [k for k in keys if k.count("/") == 2 and k.split("/")[1] in ("books", "authors", "works")]

    count = 0
    for chunk in web.group(keys, 100):
        chunk = list(chunk)
        count += len(chunk)
        update_work.do_updates(chunk)

    if count:
        logger.info("updated %d documents", count)

    return count

class Solr:
    def __init__(self):
        self.reset()

    def reset(self):
        self.total_docs = 0
        self.t_start = time.time()

    def commit(self, ndocs):
        """Performs solr commit only if there are sufficient number
        of documents or enough time has been passed since last commit.
        """
        self.total_docs += ndocs

        # no documents to commit
        if not self.total_docs:
            return

        dt = time.time() - self.t_start
        if self.total_docs > 100 or dt > 60:
            logger.info("doing solr commit (%d docs updated, last commit was %0.1f seconds ago)", self.total_docs, dt)
            self._solr_commit()
            self.reset()
        else:
            logger.debug("skipping solr commit (%d docs updated, last commit was %0.1f seconds ago)", self.total_docs, dt)

    def _solr_commit(self):
        logger.info("BEGIN commit")
        update_work.solr_update(['<commit/>'])
        logger.info("END commit")


def main(
        ol_config: str,
        debugger=False,
        state_file='solr-update.state',
        exclude_edits_containing: str = None,
        ol_url='http://openlibrary.org/',
        solr_url: str = None,
        socket_timeout=10,
        load_ia_scans=False,
        commit=False,
):
    """
    :param debugger: Wait for a debugger to attach before beginning
    :param exclude_edits_containing: Don't index matching edits
    :param solr_url: If wanting to override what's in the config file
    """
    global args
    FORMAT = "%(asctime)-15s %(levelname)s %(message)s"
    logging.basicConfig(level=logging.INFO, format=FORMAT)
    logger.info("BEGIN new-solr-updater")

    if debugger:
        import debugpy

        logger.info("Enabling debugger attachment (attach if it hangs here)")
        debugpy.listen(address=('0.0.0.0', 3000))
        logger.info("Waiting for debugger to attach...")
        debugpy.wait_for_client()
        logger.info("Debugger attached to port 3000")

    # Sometimes archive.org requests blocks forever.
    # Setting a timeout will make the request fail instead of waiting forever.
    socket.setdefaulttimeout(socket_timeout)

    # set OL URL when running on a dev-instance
    if ol_url:
        host = web.lstrips(ol_url, "http://").strip("/")
        update_work.set_query_host(host)

    if solr_url:
        update_work.set_solr_base_url(solr_url)

    logger.info(str(args))
    logger.info("loading config from %s", ol_config)
    load_config(ol_config)

    offset = read_state_file(state_file)

    logfile = InfobaseLog(config.get('infobase_server'),
                          exclude=exclude_edits_containing)
    logfile.seek(offset)

    solr = Solr()

    while True:
        records = logfile.read_records()
        keys = parse_log(records, load_ia_scans)
        count = update_keys(keys)

        if logfile.tell() != offset:
            offset = logfile.tell()
            logger.info("saving offset %s", offset)
            with open(state_file, "w") as f:
                f.write(offset)

        if commit:
            solr.commit(ndocs=count)
        else:
            logger.info("not doing solr commit as commit is off")

        # don't sleep after committing some records.
        # While the commit was on, some more edits might have happened.
        if count == 0:
            logger.debug("No more log records available, sleeping...")
            time.sleep(5)


if __name__ == "__main__":
    from scripts.solr_builder.solr_builder.fn_to_cli import FnToCLI
    FnToCLI(main).run()
