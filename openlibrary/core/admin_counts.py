"""
Script to read out data from thingdb and put it in couch so that it
can be queried by the /admin pages on openlibrary
"""

import logging
import datetime

import web
import yaml
import couchdb

class InvalidType(TypeError): pass

def connect_to_pg(config_file):
    """Connects to the postgres database specified in the dictionary
    `config`. Needs a top level key `db_parameters` and under that
    `database` (or `db`) at the least. If `user` and `host` are
    provided, they're used as well."""
    f = open(config_file)
    config = yaml.load(f)
    f.close()
    conf = {}
    conf["db"] = config["db_parameters"].get("database") or config["db_parameters"].get("db")
    if not conf['db']:
        raise KeyError("database/db")
    host = config["db_parameters"].get("host")
    user = config["db_parameters"].get("user") or config["db_parameters"].get("username")
    if host:
        conf["host"] = host
    if user:
        conf["user"] = user
    logging.debug(" Postgres Database : %(db)s"%conf)
    return web.database(dbn="postgres",**conf)


def connect_to_couch(config_file):
    "Connects to the couch databases"
    f = open(config_file)
    config = yaml.load(f)
    f.close()
    admin_db = config["admin"]["counts_db"]
    editions_db = config["lists"]["editions_db"]
    logging.debug(" Admin Database is %s", admin_db)
    logging.debug(" Editions Database is %s", editions_db)
    return couchdb.Database(admin_db), couchdb.Database(editions_db)

def get_range_data(infobase_db, coverstore_db, start, end):
    """Returns the number of new records of various types
    between `start` and `end`"""
    def _query_single_thing(db, typ, start, end):
        "Query the counts a single type from the things table"
        q1 = "SELECT id as id from thing where key='/type/%s'"% typ
        result = db.query(q1)
        try:
            kid = result[0].id 
        except IndexError:
            raise InvalidType("No id for type '/type/%s in the datbase"%typ)
        q2 = "select count(*) as count from thing where type=%d and created >= '%s' and created < '%s'"% (kid, start, end)
        result = db.query(q2)
        count = result[0].count
        return count

    def _query_covers(db, start, end):
        "Queries the number of covers added between start and end"
        q1 = "SELECT count(*) as count from cover where created>= '%s' and created < '%s'"% (start, end)
        result = db.query(q1)
        count = result[0].count
        return count
        
    retval = {}
    for typ in "work edition user author list".split():
        retval[typ] = _query_single_thing(infobase_db, typ, start, end)
        logging.debug(" Type : %s - %d", typ, retval[typ])
    retval["cover"] = _query_covers(coverstore_db, start, end)
    logging.debug(" Type : cover - %d", retval['cover'])
    return retval

def get_delta_data(admin_db, editions_db, yesterday):
    """Returns the number of new records of `types` by calculating the
    difference between yesterdays numbers and todays"""
    # eBooks
    retval = dict()
    current_total = editions_db.view("admin/ebooks").rows[0].value
    key = yesterday.strftime("counts-%Y-%m-%d")
    logging.debug(" Obtaining counts for ebooks between %s and today", yesterday.strftime("%Y-%m-%d"))
    try:
        last_total = admin_db[key]["total_ebooks"]
    except (couchdb.http.ResourceNotFound, KeyError):
        last_total = 0
    current_count = last_total - current_total
    retval["ebook"] = current_count
    retval["total_ebooks"] = current_total
    logging.debug(" Type : ebook - %d", retval['ebook'])
    # Subjects
    return retval

    
def store_data(db, data, date):
    uid = "counts-%s"%date
    logging.debug("Updating admin_db for %s - %s", uid, data)
    try:
        vals = db[uid]
        vals.update(data)
    except couchdb.http.ResourceNotFound:
        vals = data
        db[uid] = vals
    db.save(vals)
    

def main(infobase_config, openlibrary_config, coverstore_config, ndays = 1):
    logging.basicConfig(level=logging.DEBUG, format = "[%(levelname)s] : %(filename)s:%(lineno)d : %(message)s")
    logging.debug("Parsing config file")
    try:
        infobase_conn = connect_to_pg(infobase_config)
        coverstore_conn = connect_to_pg(coverstore_config)
        admin_db, editions_db = connect_to_couch(openlibrary_config)
    except KeyError,k:
        logging.critical("Config file section '%s' missing", k.args[0])
        return -1
    today = datetime.datetime.now()
    yesterday = today - datetime.timedelta(days = 1)
    # Delta data is gathered only for the current day
    data = get_delta_data(admin_db, editions_db, today)
    store_data(admin_db, data, yesterday.strftime("%Y-%m-%d"))
    for i in range(int(ndays)):
        yesterday = today - datetime.timedelta(days = 1)
        logging.debug("From %s to %s", yesterday, today)
        data = get_range_data(infobase_conn, coverstore_conn, yesterday.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
        store_data(admin_db, data, yesterday.strftime("%Y-%m-%d"))
        today = yesterday
    return 0
