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

    # Email source fields (for email-based downloads)
    source_type: Optional[str] = None  # 'email' or 'baidu'
    email_uid: Optional[str] = None  # IMAP UID
    email_subject: Optional[str] = None  # Email subject
    email_sender: Optional[str] = None  # Sender email
    email_date: Optional[datetime] = None  # Email date
    attachment_name: Optional[str] = None  # Original attachment filename


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
                raw_ocr_text TEXT,

                -- Email source fields (for email-based downloads)
                source_type TEXT DEFAULT 'email',
                email_uid TEXT,
                email_subject TEXT,
                email_sender TEXT,
                email_date TIMESTAMP,
                attachment_name TEXT,

                -- Metadata
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # IMPORTANT: Try to add new columns BEFORE creating indexes
        # This ensures the columns exist when we try to create indexes on them
        self._migrate_add_columns(cursor)

        # Create basic indexes
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

        # Email-specific indexes (only create if columns exist)
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_email_uid
                ON processed_files(email_uid)
            """)
        except sqlite3.OperationalError as e:
            if "no such column" in str(e).lower():
                logger.debug("idx_email_uid index skipped (column doesn't exist yet)")
            else:
                raise

        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_source_type
                ON processed_files(source_type)
            """)
        except sqlite3.OperationalError as e:
            if "no such column" in str(e).lower():
                logger.debug("idx_source_type index skipped (column doesn't exist yet)")
            else:
                raise

        self.conn.commit()
        logger.debug("Database tables created/verified")

    def _migrate_add_columns(self, cursor):
        """Add new columns to existing table for migration."""
        new_columns = [
            ("source_type", "TEXT DEFAULT 'email'"),
            ("email_uid", "TEXT"),
            ("email_subject", "TEXT"),
            ("email_sender", "TEXT"),
            ("email_date", "TIMESTAMP"),
            ("attachment_name", "TEXT"),
            ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        ]

        for column_name, column_def in new_columns:
            try:
                cursor.execute(
                    f"ALTER TABLE processed_files ADD COLUMN {column_name} {column_def}"
                )
                logger.debug(f"Added column: {column_name}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    pass  # Column already exists
                else:
                    logger.warning(f"Migration warning for {column_name}: {e}")

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

        email_date = record.email_date
        if email_date and isinstance(email_date, datetime):
            email_date = email_date.isoformat()

        try:
            cursor.execute("""
                INSERT INTO processed_files (
                    remote_path, local_path, final_path, file_hash,
                    processed_at, invoice_type, invoice_date, amount,
                    traveler, status, error_message, raw_ocr_text,
                    source_type, email_uid, email_subject, email_sender,
                    email_date, attachment_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                record.raw_ocr_text,
                record.source_type or 'email',
                record.email_uid,
                record.email_subject,
                record.email_sender,
                email_date,
                record.attachment_name
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
                    amount = ?, traveler = ?, status = ?, error_message = ?,
                    updated_at = CURRENT_TIMESTAMP
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
        # Get column keys
        keys = row.keys()

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
            source_type=row["source_type"] if "source_type" in keys else None,
            email_uid=row["email_uid"] if "email_uid" in keys else None,
            email_subject=row["email_subject"] if "email_subject" in keys else None,
            email_sender=row["email_sender"] if "email_sender" in keys else None,
            email_date=datetime.fromisoformat(row["email_date"]) if row["email_date"] and "email_date" in keys else None,
            attachment_name=row["attachment_name"] if "attachment_name" in keys else None,
        )

    def is_email_processed(self, email_uid: str, attachment_name: str) -> bool:
        """
        Check if an email attachment has been processed.

        Args:
            email_uid: Email UID
            attachment_name: Attachment filename

        Returns:
            bool: True if processed
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT 1 FROM processed_files
               WHERE email_uid = ? AND attachment_name = ?
               LIMIT 1""",
            (email_uid, attachment_name)
        )
        return cursor.fetchone() is not None

    def get_known_email_uids(self) -> Set[str]:
        """
        Get set of all processed email UIDs.

        Returns:
            Set[str]: Set of email UIDs
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT DISTINCT email_uid FROM processed_files WHERE email_uid IS NOT NULL"
        )
        return {row[0] for row in cursor.fetchall() if row[0]}

    def get_known_files(self) -> Set[str]:
        """
        Get set of all processed identifiers.

        Returns both old Baidu Pan paths and new email UIDs.

        Returns:
            Set[str]: Set of remote paths and email UIDs
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT remote_path FROM processed_files")
        paths = {row[0] for row in cursor.fetchall()}

        # Add email UIDs
        cursor.execute("SELECT email_uid FROM processed_files WHERE email_uid IS NOT NULL")
        uids = {row[0] for row in cursor.fetchall() if row[0]}

        return paths | uids

    def get_count(self) -> int:
        """
        Get total count of processed records.

        Returns:
            int: Total number of records
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM processed_files")
        return cursor.fetchone()[0]

    def get_count_today(self) -> int:
        """
        Get count of records processed today.

        Returns:
            int: Number of records processed today
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM processed_files
            WHERE DATE(processed_at) = DATE('now')
        """)
        return cursor.fetchone()[0]

    def get_stats_by_type(self) -> Dict[str, int]:
        """
        Get statistics grouped by invoice type.

        Returns:
            Dict mapping type to count
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT invoice_type, COUNT(*)
            FROM processed_files
            WHERE invoice_type IS NOT NULL
            GROUP BY invoice_type
        """)
        return {row[0]: row[1] for row in cursor.fetchall()}

    def get_stats_by_date(self, days: int = 30) -> List[Dict]:
        """
        Get statistics grouped by date.

        Args:
            days: Number of days to include

        Returns:
            List of date statistics
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT DATE(processed_at) as date, COUNT(*) as count
            FROM processed_files
            WHERE DATE(processed_at) >= DATE('now', '-' || ? || ' days')
            GROUP BY DATE(processed_at)
            ORDER BY date DESC
        """, (days,))
        return [{'date': row[0], 'count': row[1]} for row in cursor.fetchall()]

    def get_records(self, limit: int = 50, offset: int = 0) -> List[ProcessedRecord]:
        """
        Get paginated list of records.

        Args:
            limit: Maximum number of records to return
            offset: Number of records to skip

        Returns:
            List of ProcessedRecord objects
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM processed_files
            ORDER BY processed_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        return [self._row_to_record(row) for row in cursor.fetchall()]

    def get_record_by_id(self, record_id: int) -> Optional[ProcessedRecord]:
        """
        Get a specific record by ID.

        Args:
            record_id: Record ID

        Returns:
            ProcessedRecord or None
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM processed_files WHERE id = ?", (record_id,))
        row = cursor.fetchone()
        return self._row_to_record(row) if row else None

    def get_last_run_time(self) -> Optional[str]:
        """
        Get the timestamp of the last processed record.

        Returns:
            ISO format timestamp string or None
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT processed_at FROM processed_files
            ORDER BY processed_at DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        return row[0] if row else None

    def get_monthly_stats(self, months: int = 12) -> List[Dict]:
        """
        Get monthly statistics.

        Args:
            months: Number of months to include

        Returns:
            List of monthly statistics
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                strftime('%Y-%m', processed_at) as month,
                COUNT(*) as count,
                SUM(amount) as total_amount
            FROM processed_files
            WHERE processed_at >= DATE('now', '-' || ? || ' months')
            GROUP BY strftime('%Y-%m', processed_at)
            ORDER BY month DESC
        """, (months,))
        return [
            {
                'month': row[0],
                'count': row[1],
                'total_amount': float(row[2]) if row[2] else 0.0
            }
            for row in cursor.fetchall()
        ]
