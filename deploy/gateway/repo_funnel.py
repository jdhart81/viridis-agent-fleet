"""Finite, aggregate-only quote and paid-outcome attribution."""
from pathlib import Path
from datetime import datetime, timezone
import sqlite3
import threading

SOURCES = frozenset({'github','direct','search','openclaw','partner_integration','other','unknown','internal'})
FIELDS = ('external_settlements','paid_results_delivered','paid_results_failed',
          'paid_results_unknown','buyer_feedback_useful')


def source(value):
    value = str(value or '').strip().lower().replace('-', '_')
    return value if value in SOURCES else 'unknown'


def paid_outcomes(records, classification_version, feedback_version):
    groups = {}
    for record in records:
        if (not isinstance(record, dict) or record.get('classification_version') != classification_version
                or record.get('surface') not in {'http-402-v2','a2a-x402-v2'}
                or record.get('self_settle') is True):
            continue
        label = source(record.get('acquisition_source'))
        if label == 'internal':
            continue
        group = groups.setdefault(label, {field: 0 for field in FIELDS})
        group['external_settlements'] += 1
        status = record.get('delivery_status')
        field = {'delivered':'paid_results_delivered','failed':'paid_results_failed'}.get(status,'paid_results_unknown')
        group[field] += 1
        feedback = record.get('buyer_feedback')
        if (status == 'delivered' and isinstance(feedback, dict)
                and feedback.get('version') == feedback_version and feedback.get('useful') is True):
            group['buyer_feedback_useful'] += 1
    return {'version':'viridis-source-outcomes-v1','by_acquisition_source':groups,
            'classification':'buyer_declared_source_on_durable_settlement_records',
            'internal_and_self_excluded':True}


class QuoteCounts:
    """Count valid unpaid quote requests, including retries; never unique people."""
    def __init__(self, path):
        self.path = str(path)
        self.lock = threading.Lock()
        self.failed = False
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with self.connect() as db:
                db.execute('CREATE TABLE IF NOT EXISTS quote_counts (source TEXT, route TEXT, count INTEGER NOT NULL, PRIMARY KEY(source,route))')
                db.execute('CREATE TABLE IF NOT EXISTS funnel_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
                db.execute('INSERT OR IGNORE INTO funnel_metadata VALUES (?,?)',('started_at',datetime.now(timezone.utc).isoformat()))
        except (OSError, sqlite3.Error):
            self.failed = True

    def connect(self):
        db = sqlite3.connect(self.path, timeout=2)
        db.execute('PRAGMA synchronous=FULL')
        return db

    def record(self, label, route):
        label = source(label)
        if label == 'internal': return
        # Caller supplies a registry-validated route. Also bound stored values.
        if not isinstance(route,str) or not route or len(route)>160: return
        try:
            with self.lock, self.connect() as db:
                db.execute('INSERT INTO quote_counts VALUES (?,?,1) ON CONFLICT(source,route) DO UPDATE SET count=count+1',(label,route))
        except (OSError, sqlite3.Error):
            self.failed = True

    def snapshot(self):
        try:
            with self.lock, self.connect() as db:
                rows = db.execute('SELECT source,route,count FROM quote_counts').fetchall()
                started = db.execute("SELECT value FROM funnel_metadata WHERE key='started_at'").fetchone()[0]
            groups = {}
            for label,route,n in rows: groups.setdefault(label,{})[route]=n
            return {'version':'viridis-quote-source-counts-v1','status':'incomplete' if self.failed else 'available',
                    'started_at':started,'by_acquisition_source':groups,
                    'classification':'valid_unpaid_http_quote_requests_including_retries_not_unique_people',
                    'internal_excluded':True,'surface':'http_x402_only'}
        except (OSError, sqlite3.Error, TypeError):
            return {'version':'viridis-quote-source-counts-v1','status':'unavailable','by_acquisition_source':None}
