import datetime
import random
import logging

from dtest import Tester, create_ks
from tools.assertions import assert_length_equal

status_messages = (
    "I''m going to the Cassandra Summit in June!",
    "C* is awesome!",
    "All your sstables are belong to us.",
    "Just turned on another 50 C* nodes at <insert tech startup here>, scales beautifully.",
    "Oh, look! Cats, on reddit!",
    "Netflix recommendations are really good, wonder why?",
    "Spotify playlists are always giving me good tunes, wonder why?"
)

clients = (
    "Android",
    "iThing",
    "Chromium",
    "Mozilla",
    "Emacs"
)

logger = logging.getLogger(__name__)


class TestWideRows(Tester):
    def test_wide_rows(self):
        self.write_wide_rows()

    def write_wide_rows(self):
        cluster = self.cluster
        cluster.populate(1).start()
        node1 = cluster.nodelist()[0]

        session = self.patient_cql_connection(node1)
        start_time = datetime.datetime.now()
        create_ks(session, 'wide_rows', 1)
        # Simple timeline:  user -> {date: value, ...}
        logger.debug('Create Table....')
        session.execute('CREATE TABLE user_events (userid text, event timestamp, value text, PRIMARY KEY (userid, event));')
        date = datetime.datetime.now()
        # Create a large timeline for each of a group of users:
        for user in ('ryan', 'cathy', 'mallen', 'joaquin', 'erin', 'ham'):
            logger.debug("Writing values for: %s" % user)
            for day in range(5000):
                date_str = (date + datetime.timedelta(day)).strftime("%Y-%m-%d")
                client = random.choice(clients)
                msg = random.choice(status_messages)
                query = "UPDATE user_events SET value = '{msg:%s, client:%s}' WHERE userid='%s' and event='%s';" % (msg, client, user, date_str)
                # logger.debug(query)
                session.execute(query)

        # logger.debug('Duration of test: %s' % (datetime.datetime.now() - start_time))

        # Pick out an update for a specific date:
        query = "SELECT value FROM user_events WHERE userid='ryan' and event='%s'" % \
                (date + datetime.timedelta(10)).strftime("%Y-%m-%d")
        rows = session.execute(query)
        for value in rows:
            logger.debug(value)
            assert len(value[0]) > 0

    def test_column_index_stress(self):
        """Write a large number of columns to a single row and set
        'column_index_size_in_kb' to a sufficiently low value to force
        the creation of a column index. The test will then randomly
        read columns from that row and ensure that all data is
        returned. See CASSANDRA-5225.
        """
        cluster = self.cluster
        cluster.populate(1).start()
        (node1,) = cluster.nodelist()
        cluster.set_configuration_options(values={'column_index_size_in_kb': 1})  # reduce this value to force column index creation
        session = self.patient_cql_connection(node1)
        create_ks(session, 'wide_rows', 1)

        create_table_query = 'CREATE TABLE test_table (row varchar, name varchar, value int, PRIMARY KEY (row, name));'
        session.execute(create_table_query)

        # Now insert 100,000 columns to row 'row0'
        insert_column_query = "UPDATE test_table SET value = {value} WHERE row = '{row}' AND name = '{name}';"
        for i in range(100000):
            row = 'row0'
            name = 'val' + str(i)
            session.execute(insert_column_query.format(value=i, row=row, name=name))

        # now randomly fetch columns: 1 to 3 at a time
        for i in range(10000):
            select_column_query = "SELECT value FROM test_table WHERE row='row0' AND name in ('{name1}', '{name2}', '{name3}');"
            values2fetch = [str(random.randint(0, 99999)) for i in range(3)]
            # values2fetch is a list of random values.  Because they are random, they will not be unique necessarily.
            # To simplify the template logic in the select_column_query I will not expect the query to
            # necessarily return 3 values.  Hence I am computing the number of unique values in values2fetch
            # and using that in the assert at the end.
            expected_rows = len(set(values2fetch))
            rows = list(session.execute(select_column_query.format(name1="val" + values2fetch[0],
                                                                   name2="val" + values2fetch[1],
                                                                   name3="val" + values2fetch[2])))
            assert_length_equal(rows, expected_rows)
