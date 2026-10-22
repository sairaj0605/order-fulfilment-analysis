CREATE TABLE orders (
 order_id INTEGER PRIMARY KEY, region TEXT NOT NULL,
 created_date TEXT NOT NULL, promised_date TEXT NOT NULL,
 ordered_units INTEGER NOT NULL CHECK(ordered_units > 0), cancelled INTEGER NOT NULL CHECK(cancelled IN(0,1))
);
CREATE TABLE shipments (
 shipment_id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(order_id),
 ship_date TEXT NOT NULL, shipped_units INTEGER NOT NULL CHECK(shipped_units > 0)
);
CREATE INDEX shipments_order_date ON shipments(order_id, ship_date);
