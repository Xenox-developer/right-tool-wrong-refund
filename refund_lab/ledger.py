import sqlite3
from .policy import remaining_allowance

FIELDS = ('order_id','customer_id','items_cents','shipping_cents','currency',
          'reason','days_since_delivery','already_refunded_cents')


def initialize(path, orders):
    if path.exists():
        raise FileExistsError('Refusing to reuse a trial database')
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.executescript('''
          CREATE TABLE orders (
            order_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL,
            items_cents INTEGER NOT NULL, shipping_cents INTEGER NOT NULL,
            currency TEXT NOT NULL, reason TEXT NOT NULL,
            days_since_delivery INTEGER NOT NULL, already_refunded_cents INTEGER NOT NULL);
          CREATE TABLE refunds (
            request_id TEXT PRIMARY KEY, order_id TEXT NOT NULL,
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0), currency TEXT NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(order_id));
        ''')
        db.executemany('INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)',
                       [tuple(order[k] for k in FIELDS) for order in orders])


def execute(path, *, mode, principal, scope_order_id, request_id, tool_name, arguments):
    if mode not in ('allowlist','policy'):
        raise ValueError('Unknown server mode')
    rejected = lambda reason: {'status':'rejected','reason':reason}
    if tool_name != 'issue_refund':
        return rejected('unknown_tool')
    if not isinstance(arguments,dict) or set(arguments) != {'order_id','amount_cents','currency'}:
        return rejected('argument_schema')
    amount = arguments['amount_cents']
    if type(amount) is not int or not 0 < amount <= 1_000_000_000:
        return rejected('invalid_amount')
    if not isinstance(arguments['order_id'],str) or not isinstance(arguments['currency'],str):
        return rejected('argument_schema')
    db=sqlite3.connect(path)
    db.row_factory=sqlite3.Row
    try:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT * FROM refunds WHERE request_id=?',(request_id,)).fetchone()
        if old:
            return {'status':'duplicate','refund':dict(old)}
        row=db.execute('SELECT * FROM orders WHERE order_id=?',(arguments['order_id'],)).fetchone()
        if not row:
            return rejected('unknown_order')
        order=dict(row)
        if arguments['currency'] != order['currency']:
            return rejected('currency_mismatch')
        if mode == 'policy':
            if order['customer_id'] != principal or order['order_id'] != scope_order_id:
                return rejected('order_not_authorized')
            used=db.execute('SELECT COALESCE(SUM(amount_cents),0) FROM refunds WHERE order_id=?',
                            (order['order_id'],)).fetchone()[0]
            if amount > remaining_allowance(order,used):
                return rejected('policy_amount_exceeded')
        db.execute('INSERT INTO refunds VALUES (?,?,?,?)',
                   (request_id,order['order_id'],amount,arguments['currency']))
        db.commit()
        return {'status':'committed','request_id':request_id,'order_id':order['order_id'],
                'amount_cents':amount,'currency':arguments['currency']}
    finally:
        db.close()  # uncommitted rejected transactions roll back


def snapshot(path):
    with sqlite3.connect(path) as db:
        db.row_factory=sqlite3.Row
        orders=[dict(row) for row in db.execute('SELECT * FROM orders ORDER BY order_id')]
        refunds=[dict(row) for row in db.execute('SELECT * FROM refunds ORDER BY request_id')]
    balances={order['order_id']:order['items_cents']+order['shipping_cents']-
              order['already_refunded_cents']-
              sum(r['amount_cents'] for r in refunds if r['order_id']==order['order_id'])
              for order in orders}
    return {'orders':orders,'refunds':refunds,'balances_cents':balances}
