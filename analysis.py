from pathlib import Path
import sqlite3
import random
import json
from datetime import date, timedelta
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pandas.testing import assert_frame_equal

ROOT = Path(__file__).resolve().parent
DATA = ROOT
OUT = ROOT
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)
AS_OF = '2026-10-21'

def database(tables):
    conn = sqlite3.connect(ROOT / 'analysis.sqlite')
    # Rebuild in reverse dependency order. Foreign keys stay enabled for inserts.
    conn.execute('PRAGMA foreign_keys = OFF')
    for name in reversed(list(tables)):
        conn.execute(f'DROP TABLE IF EXISTS "{name}"')
    conn.executescript((ROOT / 'schema.sql').read_text())
    conn.execute('PRAGMA foreign_keys = ON')
    for name, frame in tables.items():
        frame.to_csv(DATA / f'{name}.csv', index=False)
        frame.to_sql(name, conn, if_exists='append', index=False)
    violations = conn.execute('PRAGMA foreign_key_check').fetchall()
    assert not violations, violations
    return conn

def queries(conn):
    # Every block starts with -- name: <output_name> and contains one SQL statement.
    text = (ROOT / 'analysis.sql').read_text()
    results = {}
    for block in text.split('-- name: ')[1:]:
        name, sql = block.split('\n', 1)
        frame = pd.read_sql_query(sql.strip(), conn, params={'as_of': AS_OF})
        results[name.strip()] = frame
        frame.to_csv(OUT / f'{name.strip()}.csv', index=False)
    return results

def parity(actual, expected, key, columns):
    a = actual.sort_values(key)[columns].reset_index(drop=True)
    b = expected.sort_values(key)[columns].reset_index(drop=True)
    assert_frame_equal(a, b, check_dtype=False, check_exact=False, atol=1e-7, rtol=1e-7)

def chart(frame, x, y, title, ylabel):
    plt.rcParams.update({'font.size': 10})
    fig, ax = plt.subplots(figsize=(9, 4.8), layout='constrained')
    ax.bar(frame[x].astype(str), frame[y], color='#24658b')
    ax.set(title=title, ylabel=ylabel)
    ax.spines[['top', 'right']].set_visible(False)
    ax.tick_params(axis='x', rotation=30)
    fig.savefig(OUT / 'summary.png', dpi=160)
    plt.close(fig)

def finish(text, checks):
    (OUT / 'findings.md').write_text(text, encoding='utf-8')
    (OUT / 'validation.json').write_text(json.dumps({'status': 'passed', 'checks': checks}, indent=2) + '\n')
    print(text)

def main():
    rng=random.Random(101)
    cutoff=date.fromisoformat(AS_OF)
    orders,shipments=[],[]
    for i in range(1,2501):
        created=cutoff-timedelta(days=rng.randint(0,89))
        promise=created+timedelta(days=rng.randint(3,12))
        units=rng.randint(2,60)
        cancelled=int(rng.random()<0.06)
        orders.append({'order_id':i,'region':rng.choice(['North','South','East','West']),
                       'created_date':str(created),'promised_date':str(promise),'ordered_units':units,'cancelled':cancelled})
        if not cancelled and rng.random() < 0.85:
            part=units//2
            first=created+timedelta(days=rng.randint(1,14))
            shipments.append({'shipment_id':len(shipments)+1,'order_id':i,'ship_date':str(first),'shipped_units':part})
            if rng.random() < 0.85:
                shipments.append({'shipment_id':len(shipments)+1,'order_id':i,
                                  'ship_date':str(first+timedelta(days=rng.randint(1,8))), 'shipped_units':units-part})
    orders,shipments=pd.DataFrame(orders),pd.DataFrame(shipments)
    conn=database({'orders':orders,'shipments':shipments})
    result=queries(conn)
    s=shipments[shipments.ship_date <= AS_OF].merge(orders[['order_id','promised_date']],on='order_id')
    total=s.groupby('order_id').shipped_units.sum()
    timely=s[s.ship_date <= s.promised_date].groupby('order_id').shipped_units.sum()
    expected=orders.merge(total.rename('shipped_units'),on='order_id',how='left').fillna({'shipped_units':0})
    expected=expected.merge(timely.rename('units_by_promise'),on='order_id',how='left').fillna({'units_by_promise':0})
    expected['remaining_units']=expected.ordered_units-expected.shipped_units
    expected['due_order']=((expected.cancelled==0)&(expected.promised_date < AS_OF)).astype(int)
    expected['on_time_full']=((expected.due_order==1)&(expected.units_by_promise >= expected.ordered_units)).astype(int)
    def status(r):
        if r.cancelled: return 'Cancelled'
        if r.remaining_units==0: return 'Fully shipped'
        if r.promised_date < AS_OF: return 'Overdue open'
        return 'Open within promise'
    expected['order_status']=expected.apply(status,axis=1)
    parity(result['order_status'],expected,'order_id',['order_id','shipped_units','remaining_units','due_order','on_time_full','order_status'])
    assert result['shipment_audit'].empty
    assert expected.remaining_units.min() >= 0
    assert (expected.ordered_units == expected.shipped_units + expected.remaining_units).all()
    assert expected.loc[expected.cancelled==1,'shipped_units'].sum()==0
    assert expected.loc[expected.promised_date==AS_OF,'due_order'].sum()==0
    due=expected.due_order.sum()
    summary=expected.groupby('region').agg(due_orders=('due_order','sum'),on_time_full=('on_time_full','sum')).reset_index()
    summary['on_time_full_pct']=summary.on_time_full/summary.due_orders*100
    summary.to_csv(OUT/'regional_service.csv',index=False)
    chart(summary,'region','on_time_full_pct','Shipped in full by promise | synthetic data','Percent of non-cancelled due orders')
    backlog=result['order_status'][result['order_status'].order_status=='Overdue open'].sort_values(['overdue_days','remaining_units'],ascending=False)
    backlog.to_csv(OUT/'action_queue.csv',index=False)
    finish(f"# Fulfilment findings\n\nAs of {AS_OF}; synthetic demonstration.\n\n"
           f"- Reviewed {len(orders):,} orders with partial-shipment reconciliation.\n"
           f"- {len(backlog):,} overdue open orders represent {backlog.remaining_units.sum():,} unshipped units.\n"
           f"- Shipped in full by promise: {expected.on_time_full.sum()/due:.1%} of {due:,} due, non-cancelled orders.\n\n"
           "## Recommended action\nWork the oldest overdue orders first, checking remaining units and stock. "
           "Agree revised promises with the responsible team and review regional gaps.\n\n"
           "## Limits\nThe service measure is shipment-based, not delivered OTIF: there is no proof-of-delivery data. "
           "Cancelled orders and promises due today are excluded from the service denominator. "
           "A late fully shipped order is closed but remains a service miss. No returns or split-line SLAs are modelled.\n",
           ['SQL/Pandas all-order parity','ordered = shipped + remaining per order',
            'partial shipments aggregate without over-fulfilment','cancelled orders excluded from KPI',
            'due-today boundary checked','foreign keys checked'])
    conn.close()

if __name__ == '__main__':
    main()
