"""
Database module for tracking processed invoice files.

Uses SQLite to store records of processed files and prevent duplicates.
"""

import sqlite3
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, List, Set, Dict, Any
from enum import Enum

from loguru import logger


class ProcessStatus(Enum):
    """Processing status enum"""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ProcessedRecord:
    """Record of a processed file"""
    id: Optional[int] = None
    remote_path: str = ""
    local_path: Optional[str] = None
    final_path: Optional[str] = None
    file_hash: Optional[str] = None
    processed_at: Optional[datetime] = None
    invoice_type: Optional[str] = None
    invoice_date: Optional[str] = None
    amount: Optional[float] = None
    traveler: Optional[str] = None
    status: str = ProcessStatus.SUCCESS.value
    error_message: Optional[str] = None
    raw_ocr_text: Optional[str] = None


class RecordDatabase:
    """
    Database for tracking processed invoice files.

    Stores records of files that have been processed to avoid duplicates.
    """

    def __init__(self, db_path: str = "data/records.db"):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self):
        """Establish database connection and create tables if needed."""
        try:
            self._conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0
            )
            self._conn.row_factory = sqlite3.Row
            self._create_tables()
            logger.info(f"Database connected: {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("Database connection closed")

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    @property
    def conn(self) -> sqlite3.Connection:
        """Get database connection, connecting if needed."""
        if self._conn is None:
            self.connect()
        return self._conn

    def _create_tables(self):
        """Create database tables if they don't exist."""
        cursor = self.conn.cursor()

        # Main records table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                remote_path TEXT NOT NULL UNIQUE,
                local_path TEXT,
                final_path TEXT,
                file_hash TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                invoice_type TEXT,
                invoice_date DATE,
                amount DECIMAL(10,2),
                traveler TEXT,
                status TEXT DEFAULT 'success',
                error_message TEXT,
                raw_ocr_text TEXT
            )
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_remote_path
            ON processed_files(remote_path)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_processed_at
            ON processed_files(processed_at)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_status
            ON processed_files(status)
        """)

        self.conn.commit()
        logger.debug("Database tables created/verified")

    def is_processed(self, remote_path: str) -> bool:
        """
        Check if a file has been processed.

        Args:
            remote_path: Remote file path in Baidu Pan

        Returns:
            bool: True if file has been processed
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT 1 FROM processed_files WHERE remote_path = ? LIMIT 1",
            (remote_path,)
        )
        return cursor.fetchone() is not None

    def add_record(self, record: ProcessedRecord) -> int:
        """
        Add a processed file record.

        Args:
            record: ProcessedRecord to add

        Returns:
            int: ID of inserted record
        """
        cursor = self.conn.cursor()

        # Convert datetime to string if needed
        processed_at = record.processed_at
        if processed_at and isinstance(processed_at, datetime):
            processed_at = processed_at.isoformat()

        try:
            cursor.execute("""
                INSERT INTO processed_files (
                    remote_path, local_path, final_path, file_hash,
                    processed_at, invoice_type, invoice_date, amount,
                    traveler, status, error_message, raw_ocr_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.remote_path,
                record.local_path,
                record.final_path,
                record.file_hash,
                processed_at or datetime.now().isoformat(),
                record.invoice_type,
                record.invoice_date,
                record.amount,
                record.traveler,
                record.status,
                record.error_message,
                record.raw_ocr_text
            ))
            self.conn.commit()
            record_id = cursor.lastrowid
            logger.debug(f"Added record: {record.remote_path} -> ID {record_id}")
            return record_id
        except sqlite3.IntegrityError:
            logger.warning(f"Record already exists: {record.remote_path}")
            # Update existing record
            cursor.execute("""
                UPDATE processed_files SET
                    local_path = ?, final_path = ?, file_hash = ?,
                    processed_at = ?, invoice_type = ?, invoice_date = ?,
                    amount = ?, traveler = ?, status = ?, error_message = ?
                WHERE remote_path = ?
            """, (
                record.local_path, record.final_path, record.file_hash,
                processed_at or datetime.now().isoformat(),
                record.invoice_type, record.invoice_date, record.amount,
                record.traveler, record.status, record.error_message,
                record.remote_path
            ))
            self.conn.commit()
            return cursor.lastrowid

    def get_record(self, remote_path: str) -> Optional[ProcessedRecord]:
        """
        Get a record by remote path.

        Args:
            remote_path: Remote file path

        Returns:
            ProcessedRecord if found, None otherwise
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM processed_files WHERE remote_path = ?",
            (remote_path,)
        )
        row = cursor.fetchone()
        if row:
            return self._row_to_record(row)
        return None

    def get_known_files(self) -> Set[str]:
        """
        Get set of all processed remote file paths.

        Returns:
            Set[str]: Set of remote paths
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT remote_path FROM processed_files")
        return {row[0] for row in cursor.fetchall()}

    def get_recent_records(self, limit: int = 100) -> List[ProcessedRecord]:
        """
        Get recently processed records.

        Args:
            limit: Maximum number of records to return

        Returns:
            List[ProcessedRecord]: List of recent records
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM processed_files
            ORDER BY processed_at DESC
            LIMIT ?
        """, (limit,))
        return [self._row_to_record(row) for row in cursor.fetchall()]

    def get_failed_records(self) -> List[ProcessedRecord]:
        """
        Get records with failed status.

        Returns:
            List[ProcessedRecord]: List of failed records
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM processed_files
            WHERE status = 'failed'
            ORDER BY processed_at DESC
        """)
        return [self._row_to_record(row) for row in cursor.fetchall()]

    def delete_record(self, remote_path: str) -> bool:
        """
        Delete a record by remote path.

        Args:
            remote_path: Remote file path

        Returns:
            bool: True if record was deleted
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM processed_files WHERE remote_path = ?",
            (remote_path,)
        )
        self.conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.debug(f"Deleted record: {remote_path}")
        return deleted

    def update_status(self, remote_path: str, status: ProcessStatus, error_message: str = None):
        """
        Update processing status of a record.

        Args:
            remote_path: Remote file path
            status: New status
            error_message: Optional error message
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE processed_files
            SET status = ?, error_message = ?
            WHERE remote_path = ?
        """, (status.value, error_message, remote_path))
        self.conn.commit()
        logger.debug(f"Updated status: {remote_path} -> {status.value}")

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get processing statistics.

        Returns:
            Dict with statistics:
                - total: Total number of records
                - success: Number of successful records
                - failed: Number of failed records
                - by_type: Count by invoice type
                - by_traveler: Count by traveler
        """
        cursor = self.conn.cursor()

        # Total count
        cursor.execute("SELECT COUNT(*) FROM processed_files")
        total = cursor.fetchone()[0]

        # Status counts
        cursor.execute("SELECT status, COUNT(*) FROM processed_files GROUP BY status")
        status_counts = {row[0]: row[1] for row in cursor.fetchall()}

        # By invoice type
        cursor.execute("""
            SELECT invoice_type, COUNT(*)
            FROM processed_files
            WHERE invoice_type IS NOT NULL
            GROUP BY invoice_type
        """)
        by_type = {row[0]: row[1] for row in cursor.fetchall()}

        # By traveler
        cursor.execute("""
            SELECT traveler, COUNT(*)
            FROM processed_files
            WHERE traveler IS NOT NULL
            GROUP BY traveler
        """)
        by_traveler = {row[0]: row[1] for row in cursor.fetchall()}

        return {
            "total": total,
            "success": status_counts.get("success", 0),
            "failed": status_counts.get("failed", 0),
            "skipped": status_counts.get("skipped", 0),
            "by_type": by_type,
            "by_traveler": by_traveler,
        }

    def _row_to_record(self, row: sqlite3.Row) -> ProcessedRecord:
        """Convert database row to ProcessedRecord."""
        return ProcessedRecord(
            id=row["id"],
            remote_path=row["remote_path"],
            local_path=row["local_path"],
            final_path=row["final_path"],
            file_hash=row["file_hash"],
            processed_at=datetime.fromisoformat(row["processed_at"]) if row["processed_at"] else None,
            invoice_type=row["invoice_type"],
            invoice_date=row["invoice_date"],
            amount=row["amount"],
            traveler=row["traveler"],
            status=row["status"],
            error_message=row["error_message"],
            raw_ocr_text=row["raw_ocr_text"],
        )
