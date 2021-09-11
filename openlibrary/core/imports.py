"""Interface to import queue.
"""
from collections import defaultdict
import logging
import datetime
import time
import web
import json

from psycopg2.errors import UndefinedTable, UniqueViolation

from . import db

logger = logging.getLogger("openlibrary.imports")

class Batch(web.storage):
    @staticmethod
    def find(name, create=False):
        result = db.query("SELECT * FROM import_batch where name=$name", vars=locals())
        if result:
            return Batch(result[0])
        elif create:
            return Batch.new(name)

    @staticmethod
    def new(name):
        db.insert("import_batch", name=name)
        return Batch.find(name=name)

    def load_items(self, filename):
        """Adds all the items specified in the filename to this batch.
        """
        items = [line.strip() for line in open(filename) if line.strip()]
        self.add_items(items)

    def dedupe_ia_items(self, items):
        already_present = [
            row.ia_id for row in db.query(
                "SELECT ia_id FROM import_item WHERE ia_id IN $items",
                vars=locals()
            )
        ]
        # ignore already present
        logger.info(
            "batch %s: %d items are already present, ignoring...",
            self.name,
            len(already_present)
        )
        return list(set(items) - set(already_present))

    def add_items(self, items, ia_items=True):
        """
        :param ia_items: True if `items` is a list of IA identifiers, False if
        book data dicts.
        """
        if not items:
            return

        logger.info("batch %s: adding %d items", self.name, len(items))

        if ia_items:
            items = self.dedupe_ia_items(items)

        if items:
            # Either create a reference to an IA id which will be loaded
            # from Archive.org metadata, or provide json data book record
            # which will be loaded directly into the OL catalog
            values = [
                {
                    'batch_id': self.id,
                    **({'ia_id': item} if ia_items else {
                        'data': json.dumps(item, sort_keys=True)
                    })
                }
                for item in items
            ]
            try:
                # TODO: Upgrade psql and use `INSERT OR IGNORE`
                # otherwise it will fail on UNIQUE `data`
                # https://stackoverflow.com/questions/1009584
                db.get_db().multiple_insert("import_item", values)
            except UniqueViolation:
                for value in values:
                    try:
                        db.get_db().insert("import_item", **value)
                    except UniqueViolation:
                        pass
            logger.info("batch %s: added %d items", self.name, len(items))

    def get_items(self, status="pending"):
        result = db.where("import_item", batch_id=self.id, status=status)
        return [ImportItem(row) for row in result]

class ImportItem(web.storage):
    @staticmethod
    def find_pending(limit=1000):
        result = db.where("import_item", status="pending", order="id", limit=limit)
        return [ImportItem(row) for row in result]

    @staticmethod
    def find_by_identifier(identifier):
        result = db.where("import_item", ia_id=identifier)
        if result:
            return ImportItem(result[0])

    def set_status(self, status, error=None, ol_key=None):
        id_ = self.ia_id or "%s:%s" % (self.batch_id, self.id)
        logger.info("set-status %s - %s %s %s", id_, status, error, ol_key)
        d = dict(
            status=status,
            error=error,
            ol_key=ol_key,
            import_time=datetime.datetime.utcnow())
        if status != 'failed':
            d = dict(**d, data=None)
        db.update("import_item", where="id=$id", vars=self, **d)
        self.update(d)

    def mark_failed(self, error):
        self.set_status(status='failed', error=error)

    def mark_found(self, ol_key):
        self.set_status(status='found', ol_key=ol_key)

    def mark_created(self, ol_key):
        self.set_status(status='created', ol_key=ol_key)

    def mark_modified(self, ol_key):
        self.set_status(status='modified', ol_key=ol_key)


class Stats:
    """Import Stats."""
    def get_imports_per_hour(self):
        """Returns the number imports happened in past one hour duration.
        """
        try:
            result = db.query(
                "SELECT count(*) as count FROM import_item" +
                " WHERE import_time > CURRENT_TIMESTAMP - interval '1' hour")
        except UndefinedTable:
            logger.exception("Database table import_item may not exist on localhost")
            return 0
        return result[0].count

    def get_count(self, status=None):
        where = "status=$status" if status else "1=1"
        try:
            rows = db.select("import_item",
                what="count(*) as count",
                where=where,
                vars=locals())
        except UndefinedTable:
            logger.exception("Database table import_item may not exist on localhost")
            return 0
        return rows[0].count

    def get_count_by_status(self, date=None):
        rows = db.query("SELECT status, count(*) FROM import_item GROUP BY status")
        return dict([(row.status, row.count) for row in rows])

    def get_count_by_date_status(self, ndays=10):
        try:
            result = db.query(
                "SELECT added_time::date as date, status, count(*)" +
                " FROM import_item " +
                " WHERE added_time > current_date - interval '$ndays' day"
                " GROUP BY 1, 2" +
                " ORDER BY 1 desc",
                vars=locals())
        except UndefinedTable:
            logger.exception("Database table import_item may not exist on localhost")
            return []
        d = defaultdict(dict)
        for row in result:
            d[row.date][row.status] = row.count
        return sorted(d.items(), reverse=True)

    def get_books_imported_per_day(self):
        try:
            rows = db.query(
                "SELECT import_time::date as date, count(*) as count"
                " FROM import_item" +
                " WHERE status='created'"
                " GROUP BY 1" +
                " ORDER BY 1")
        except UndefinedTable:
            logger.exception("Database table import_item may not exist on localhost")
            return []
        return [[self.date2millis(row.date), row.count] for row in rows]

    def date2millis(self, date):
        return time.mktime(date.timetuple()) * 1000

    def get_items(self, date=None, order=None, limit=None):
        """Returns all rows with given added date.
        """
        where = "added_time::date = $date" if date else "1 = 1"
        try:
            return db.select("import_item",
                where=where,
                order=order,
                limit=limit,
                vars=locals())
        except UndefinedTable:
            logger.exception("Database table import_item may not exist on localhost")
            return []

    def get_items_summary(self, date):
        """Returns all rows with given added date.
        """
        rows = db.query(
                "SELECT status, count(*) as count" +
                " FROM import_item" +
                " WHERE added_time::date = $date"
                " GROUP BY status",
                vars=locals())
        return {
            "counts": dict([(row.status, row.count) for row in rows])
        }
