-- name: order_status
WITH shipped AS (
 SELECT order_id, SUM(shipped_units) AS shipped_units,
 MAX(ship_date) AS last_ship_date,
 SUM(CASE WHEN ship_date <= o.promised_date THEN shipped_units ELSE 0 END) AS units_by_promise
 FROM shipments s JOIN orders o USING(order_id)
 WHERE ship_date <= date(:as_of) GROUP BY order_id
)
SELECT o.*, COALESCE(s.shipped_units,0) AS shipped_units,
 o.ordered_units - COALESCE(s.shipped_units,0) AS remaining_units,
 CASE WHEN cancelled=1 THEN 'Cancelled'
      WHEN COALESCE(s.shipped_units,0) >= o.ordered_units THEN 'Fully shipped'
      WHEN promised_date < date(:as_of) THEN 'Overdue open'
      ELSE 'Open within promise' END AS order_status,
 CASE WHEN cancelled=0 AND promised_date < date(:as_of)
      AND COALESCE(s.units_by_promise,0) >= o.ordered_units THEN 1 ELSE 0 END AS on_time_full,
 CASE WHEN cancelled=0 AND promised_date < date(:as_of) THEN 1 ELSE 0 END AS due_order,
 CASE WHEN cancelled=0 AND o.ordered_units > COALESCE(s.shipped_units,0)
      AND promised_date < date(:as_of)
      THEN CAST(julianday(:as_of)-julianday(promised_date) AS INTEGER) ELSE 0 END AS overdue_days
FROM orders o LEFT JOIN shipped s USING(order_id)
WHERE created_date <= date(:as_of) ORDER BY order_id;

-- name: shipment_audit
SELECT o.order_id, o.ordered_units, COALESCE(SUM(s.shipped_units),0) AS all_scheduled_units
FROM orders o LEFT JOIN shipments s USING(order_id)
GROUP BY o.order_id HAVING COALESCE(SUM(s.shipped_units),0) > o.ordered_units;
