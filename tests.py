"""Small deterministic fixtures exercising business boundaries in the actual SQL."""
from pathlib import Path
import sqlite3
import unittest

ROOT = Path(__file__).resolve().parent
AS_OF = '2026-10-21'


def fixture(folder):
    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    connection.executescript((ROOT / 'schema.sql').read_text())
    blocks = (ROOT / 'analysis.sql').read_text().split('-- name: ')[1:]
    sql = dict(block.split('\n', 1) for block in blocks)
    return connection, {k.strip(): v for k, v in sql.items()}


class BusinessBoundaries(unittest.TestCase):
    def test_fulfilment_partial_late_cancelled_and_due_today(self):
            c, q = fixture('03-order-fulfilment')
            self.addCleanup(c.close)
            c.executemany('INSERT INTO orders VALUES(?,?,?,?,?,?)',
                          [(1,'N','2026-10-01','2026-10-10',10,0),
                           (2,'N','2026-10-01','2026-10-10',10,0),
                           (3,'N','2026-10-01','2026-10-21',10,0),
                           (4,'N','2026-10-01','2026-10-10',10,1)])
            c.executemany('INSERT INTO shipments VALUES(?,?,?,?)',
                          [(1,1,'2026-10-09',4),(2,1,'2026-10-11',6),
                           (3,2,'2026-10-09',4),(4,2,'2026-10-22',6)])
            r = {x['order_id']: dict(x) for x in c.execute(q['order_status'], {'as_of': AS_OF})}
            self.assertEqual(r[1]['order_status'], 'Fully shipped')
            self.assertEqual(r[1]['on_time_full'], 0)
            self.assertEqual(r[1]['due_order'], 1)
            self.assertEqual(r[2]['remaining_units'], 6)
            self.assertEqual(r[2]['order_status'], 'Overdue open')
            self.assertEqual(r[3]['due_order'], 0)
            self.assertEqual(r[4]['due_order'], 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)
