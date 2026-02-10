"""SQLite database for storing metrics, price history, alerts, and DCA portfolios."""
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from models.metrics import CombinedSnapshot

logger = logging.getLogger("btcmonitor.db")


class Database:
    def __init__(self, db_path="data/bitcoin.db"):
        self.db_path = db_path
        self.conn = None

    def connect(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()
        return self

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS metrics_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                price_usd REAL,
                market_cap REAL,
                volume_24h REAL,
                change_24h_pct REAL,
                hash_rate_th REAL,
                difficulty REAL,
                block_time_avg REAL,
                difficulty_change_pct REAL,
                supply_circulating REAL,
                fear_greed_value INTEGER,
                fear_greed_label TEXT,
                btc_gold_ratio REAL,
                btc_dominance_pct REAL,
                mvrv_ratio REAL,
                mvrv_z_score REAL,
                source TEXT DEFAULT 'api'
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp
                ON metrics_snapshots(timestamp);

            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                price_usd REAL NOT NULL,
                market_cap REAL,
                volume REAL
            );

            CREATE INDEX IF NOT EXISTS idx_price_date
                ON price_history(date);

            CREATE TABLE IF NOT EXISTS alert_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id TEXT NOT NULL,
                rule_name TEXT NOT NULL,
                metric_value REAL,
                threshold REAL,
                severity TEXT NOT NULL,
                message TEXT,
                triggered_at TEXT NOT NULL,
                acknowledged INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_alerts_triggered
                ON alert_history(triggered_at);

            CREATE TABLE IF NOT EXISTS dca_portfolios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                start_date TEXT,
                frequency TEXT DEFAULT 'weekly',
                amount REAL DEFAULT 100,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dca_purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                price_usd REAL NOT NULL,
                btc_amount REAL NOT NULL,
                usd_amount REAL NOT NULL,
                FOREIGN KEY (portfolio_id) REFERENCES dca_portfolios(id)
            );

            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                target_btc REAL,
                target_usd REAL,
                monthly_dca REAL DEFAULT 200,
                target_date TEXT,
                created_at TEXT NOT NULL
            );
        """)
        self.conn.commit()

    # --- Metrics Snapshots ---

    def save_snapshot(self, snapshot: CombinedSnapshot):
        d = snapshot.to_dict()
        self.conn.execute("""
            INSERT INTO metrics_snapshots
            (timestamp, price_usd, market_cap, volume_24h, change_24h_pct,
             hash_rate_th, difficulty, block_time_avg, difficulty_change_pct,
             supply_circulating, fear_greed_value, fear_greed_label,
             btc_gold_ratio, btc_dominance_pct, mvrv_ratio, mvrv_z_score, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            d["timestamp"], d["price_usd"], d["market_cap"], d["volume_24h"],
            d["change_24h_pct"], d["hash_rate_th"], d["difficulty"],
            d["block_time_avg"], d["difficulty_change_pct"], d["supply_circulating"],
            d["fear_greed_value"], d["fear_greed_label"], d["btc_gold_ratio"],
            d["btc_dominance_pct"], d["mvrv_ratio"], d["mvrv_z_score"], d["source"],
        ))
        self.conn.commit()
        logger.debug(f"Saved snapshot at {d['timestamp']}")

    def get_latest_snapshot(self):
        row = self.conn.execute(
            "SELECT * FROM metrics_snapshots ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return CombinedSnapshot.from_dict(dict(row))

    def get_snapshots(self, start=None, end=None, limit=1000):
        query = "SELECT * FROM metrics_snapshots WHERE 1=1"
        params = []
        if start:
            query += " AND timestamp >= ?"
            params.append(start.isoformat() if hasattr(start, 'isoformat') else start)
        if end:
            query += " AND timestamp <= ?"
            params.append(end.isoformat() if hasattr(end, 'isoformat') else end)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [CombinedSnapshot.from_dict(dict(r)) for r in rows]

    def get_metric_history(self, metric_column, days=30):
        """Get historical values of a specific metric column."""
        rows = self.conn.execute(f"""
            SELECT timestamp, {metric_column} as value
            FROM metrics_snapshots
            WHERE {metric_column} IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT ?
        """, (days * 24,)).fetchall()  # Assume ~hourly snapshots, get enough
        return [(r["timestamp"], r["value"]) for r in reversed(rows)]

    # --- Price History ---

    def save_price_history(self, records):
        self.conn.executemany("""
            INSERT OR REPLACE INTO price_history (date, price_usd, market_cap, volume)
            VALUES (?, ?, ?, ?)
        """, [(r["date"], r["price_usd"], r.get("market_cap", 0), r.get("volume", 0))
              for r in records])
        self.conn.commit()
        logger.debug(f"Saved {len(records)} price history records")

    def get_price_history(self, start_date=None, end_date=None):
        query = "SELECT * FROM price_history WHERE 1=1"
        params = []
        if start_date:
            query += " AND date >= ?"
            params.append(str(start_date))
        if end_date:
            query += " AND date <= ?"
            params.append(str(end_date))
        query += " ORDER BY date ASC"
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_price_for_date(self, target_date):
        """Get price for exact date or nearest prior date."""
        row = self.conn.execute("""
            SELECT * FROM price_history
            WHERE date <= ? ORDER BY date DESC LIMIT 1
        """, (str(target_date),)).fetchone()
        return dict(row) if row else None

    def get_price_history_count(self):
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM price_history").fetchone()
        return row["cnt"]

    def get_price_date_range(self):
        row = self.conn.execute(
            "SELECT MIN(date) as min_date, MAX(date) as max_date FROM price_history"
        ).fetchone()
        return dict(row) if row else {"min_date": None, "max_date": None}

    def get_price_history_stats(self):
        """Get price history availability statistics for conditional UI rendering."""
        try:
            row = self.conn.execute("""
                SELECT
                    COUNT(DISTINCT date) as total_days,
                    MIN(date) as earliest_date,
                    MAX(date) as latest_date
                FROM price_history
            """).fetchone()

            if not row or row["total_days"] == 0:
                return {
                    "total_days": 0,
                    "earliest_date": None,
                    "latest_date": None,
                    "has_sufficient_data": False
                }

            return {
                "total_days": row["total_days"],
                "earliest_date": row["earliest_date"],
                "latest_date": row["latest_date"],
                "has_sufficient_data": row["total_days"] >= 365
            }
        except sqlite3.OperationalError:
            # Table doesn't exist yet
            return {
                "total_days": 0,
                "earliest_date": None,
                "latest_date": None,
                "has_sufficient_data": False
            }

    def has_data_for_range(self, start_date, end_date):
        """Check if we have price data for a specific date range."""
        try:
            row = self.conn.execute("""
                SELECT COUNT(*) as cnt FROM price_history
                WHERE date >= ? AND date <= ?
            """, (str(start_date), str(end_date))).fetchone()

            # Consider "has data" if we have at least some coverage (50% of expected days)
            from datetime import datetime
            start = datetime.fromisoformat(str(start_date))
            end = datetime.fromisoformat(str(end_date))
            expected_days = (end - start).days

            return row["cnt"] >= (expected_days * 0.5)
        except (sqlite3.OperationalError, ValueError):
            return False

    # --- Alert History ---

    def save_alert(self, record):
        self.conn.execute("""
            INSERT INTO alert_history
            (rule_id, rule_name, metric_value, threshold, severity, message, triggered_at, acknowledged)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.rule_id, record.rule_name, record.metric_value,
            record.threshold, record.severity, record.message,
            record.triggered_at.isoformat(), int(record.acknowledged),
        ))
        self.conn.commit()

    def get_recent_alerts(self, limit=50):
        rows = self.conn.execute("""
            SELECT * FROM alert_history ORDER BY triggered_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_last_alert_time(self, rule_id):
        row = self.conn.execute("""
            SELECT triggered_at FROM alert_history
            WHERE rule_id = ? ORDER BY triggered_at DESC LIMIT 1
        """, (rule_id,)).fetchone()
        if row:
            return datetime.fromisoformat(row["triggered_at"])
        return None

    def get_alert_stats(self, days=30):
        rows = self.conn.execute("""
            SELECT severity, COUNT(*) as count
            FROM alert_history
            WHERE triggered_at >= datetime('now', ?)
            GROUP BY severity
        """, (f"-{days} days",)).fetchall()
        return {r["severity"]: r["count"] for r in rows}

    def acknowledge_alert(self, alert_id):
        self.conn.execute(
            "UPDATE alert_history SET acknowledged = 1 WHERE id = ?", (alert_id,)
        )
        self.conn.commit()

    # --- DCA Portfolios ---

    def create_portfolio(self, name, start_date, frequency, amount):
        cur = self.conn.execute("""
            INSERT INTO dca_portfolios (name, start_date, frequency, amount, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (name, str(start_date), frequency, amount, datetime.now(timezone.utc).isoformat()))
        self.conn.commit()
        return cur.lastrowid

    def add_purchase(self, portfolio_id, purchase_date, price, btc_amount, usd_amount):
        self.conn.execute("""
            INSERT INTO dca_purchases (portfolio_id, date, price_usd, btc_amount, usd_amount)
            VALUES (?, ?, ?, ?, ?)
        """, (portfolio_id, str(purchase_date), price, btc_amount, usd_amount))
        self.conn.commit()

    def get_portfolio(self, portfolio_id):
        port = self.conn.execute(
            "SELECT * FROM dca_portfolios WHERE id = ?", (portfolio_id,)
        ).fetchone()
        if not port:
            return None
        purchases = self.conn.execute(
            "SELECT * FROM dca_purchases WHERE portfolio_id = ? ORDER BY date ASC",
            (portfolio_id,)
        ).fetchall()
        result = dict(port)
        result["purchases"] = [dict(p) for p in purchases]
        return result

    def get_price_gaps(self, start_date: str, end_date: str, max_gap_days: int = 3) -> list[tuple[str, str]]:
        """Find gaps in price_history where consecutive missing days exceed max_gap_days."""
        from datetime import date as d, timedelta
        rows = self.conn.execute(
            "SELECT date FROM price_history WHERE date BETWEEN ? AND ? ORDER BY date",
            (start_date, end_date)
        ).fetchall()
        existing = {r["date"] for r in rows}

        gaps = []
        start = d.fromisoformat(start_date)
        end = d.fromisoformat(end_date)
        gap_start = None
        gap_len = 0
        current = start

        while current <= end:
            ds = current.isoformat()
            if ds not in existing:
                if gap_start is None:
                    gap_start = ds
                gap_len += 1
            else:
                if gap_start and gap_len >= max_gap_days:
                    gaps.append((gap_start, (current - timedelta(days=1)).isoformat()))
                gap_start = None
                gap_len = 0
            current += timedelta(days=1)

        if gap_start and gap_len >= max_gap_days:
            gaps.append((gap_start, end_date))

        return gaps

    def get_nearest_snapshot(self, target_timestamp: str) -> dict | None:
        """Return the metrics_snapshot closest to target_timestamp (but not after)."""
        row = self.conn.execute("""
            SELECT * FROM metrics_snapshots
            WHERE timestamp <= ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (target_timestamp,)).fetchone()
        return dict(row) if row else None

    def list_portfolios(self):
        rows = self.conn.execute("""
            SELECT p.*, COUNT(pu.id) as num_purchases,
                   COALESCE(SUM(pu.usd_amount), 0) as total_invested,
                   COALESCE(SUM(pu.btc_amount), 0) as total_btc
            FROM dca_portfolios p
            LEFT JOIN dca_purchases pu ON p.id = pu.portfolio_id
            GROUP BY p.id
            ORDER BY p.created_at DESC
        """).fetchall()
        return [dict(r) for r in rows]
