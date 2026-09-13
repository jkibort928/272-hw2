# Author: Jack Kibort
"""
Lightweight persistence for processed webhook deliveries.

Uses SQLite so state survives process restarts. The GitHub delivery id
(`X-GitHub-Delivery`) plus the action is used as the dedupe key: if we
have already recorded that (delivery_id, action) pair, we treat a
redelivery as a no-op success rather than double-processing it.
"""
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class EventRecord:
    id: str
    event: str
    action: Optional[str]
    issue_number: Optional[int]
    timestamp: str


class EventStore:
    def __init__(self, db_path: str = "events.db"):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                delivery_id TEXT NOT NULL,
                action TEXT,
                event TEXT NOT NULL,
                issue_number INTEGER,
                timestamp TEXT NOT NULL,
                PRIMARY KEY (delivery_id, action)
            )
            """
        )
        self._conn.commit()

    def already_processed(self, delivery_id: str, action: Optional[str]) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM events WHERE delivery_id = ? AND action = ?",
            (delivery_id, action or ""),
        )
        return cur.fetchone() is not None

    def record(self, delivery_id: str, event: str, action: Optional[str],
               issue_number: Optional[int]) -> None:
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._conn.execute(
            """
            INSERT OR IGNORE INTO events
                (delivery_id, action, event, issue_number, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (delivery_id, action or "", event, issue_number, timestamp),
        )
        self._conn.commit()

    def recent(self, limit: int = 20) -> list[EventRecord]:
        cur = self._conn.execute(
            "SELECT delivery_id, event, action, issue_number, timestamp "
            "FROM events ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        return [
            EventRecord(id=row[0], event=row[1], action=row[2] or None,
                        issue_number=row[3], timestamp=row[4])
            for row in cur.fetchall()
        ]
