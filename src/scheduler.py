"""
Task scheduler module for automated invoice processing.

Orchestrates the complete invoice processing workflow.
"""

import time
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from loguru import logger

from .config import get_config, setup_logging
from .database import RecordDatabase, ProcessedRecord, ProcessStatus
from .bypy_sync import BypySyncManager
from .ocr_engine import OCREngine, get_ocr_engine
from .parser import InvoiceParser
from .renamer import InvoiceRenamer
from .organizer import InvoiceOrganizer


@dataclass
class TaskResult:
    """Result of a task run"""
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    errors: List[str] = field(default_factory=list)

    @property
    def duration(self) -> Optional[float]:
        """Get task duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    def __str__(self) -> str:
        return (
            f"TaskResult(total={self.total}, success={self.success}, "
            f"failed={self.failed}, skipped={self.skipped}, "
            f"duration={self.duration:.1f}s)"
        )


class TaskScheduler:
    """
    Task scheduler for automated invoice processing.

    Coordinates the complete workflow:
    1. Sync new files from Baidu Pan
    2. OCR recognition
    3. Parse invoice information
    4. Generate new filename
    5. Organize to categorized directory
    6. Record in database
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize task scheduler.

        Args:
            config_path: Optional path to configuration file
        """
        # Load configuration
        self.config = get_config()
        setup_logging(self.config.logging)

        # Initialize components
        self.db = RecordDatabase(str(self.config.get_db_path()))
        self.sync_manager = BypySyncManager()
        self.ocr_engine = get_ocr_engine()
        self.parser = InvoiceParser()
        self.renamer = InvoiceRenamer()
        self.organizer = InvoiceOrganizer()

        # APScheduler instance
        self.scheduler: Optional[BlockingScheduler] = None

        logger.info("TaskScheduler initialized")

    def run_once(self, dry_run: bool = False) -> TaskResult:
        """
        Run the complete invoice processing workflow once.

        Args:
            dry_run: If True, simulate without actually moving files

        Returns:
            TaskResult: Processing result statistics
        """
        result = TaskResult(start_time=datetime.now())

        logger.info("=" * 60)
        logger.info("Starting invoice processing task")
        if dry_run:
            logger.info("[DRY RUN MODE - No files will be moved]")
        logger.info("=" * 60)

        try:
            # Connect to database
            self.db.connect()

            # Step 1: Get known files
            known_files = self.db.get_known_files()
            logger.info(f"Known files in database: {len(known_files)}")

            # Step 2: Sync new files from Baidu Pan
            logger.info("Step 1: Syncing files from Baidu Pan...")
            new_files = self.sync_manager.sync_new_files(known_files)
            logger.info(f"Found {len(new_files)} new files")

            if not new_files:
                logger.info("No new files to process")
                result.end_time = datetime.now()
                return result

            result.total = len(new_files)

            # Step 3: Process each file
            for file_path in new_files:
                try:
                    self._process_file(file_path, dry_run, result)
                except Exception as e:
                    logger.error(f"Error processing {file_path}: {e}")
                    result.failed += 1
                    result.errors.append(f"{file_path}: {str(e)}")

            # Step 4: Cleanup temp files
            if self.config.options.delete_temp_after_process and not dry_run:
                logger.info("Cleaning up temp directory...")
                self._cleanup_temp(new_files)

            # Step 5: Match car invoices with trip receipts
            if not dry_run:
                logger.info("Step 5: Matching car invoices with trip receipts...")
                from .invoice_matcher import InvoiceMatcher
                matcher = InvoiceMatcher(self.config.local_output_dir)
                matched_count = matcher.match_and_rename_invoices()
                logger.info(f"Matched {matched_count} car invoices")

        except Exception as e:
            logger.error(f"Task failed: {e}")
            result.errors.append(str(e))

        finally:
            self.db.close()
            result.end_time = datetime.now()

        # Log summary
        logger.info("=" * 60)
        logger.info(f"Task completed: {result}")
        logger.info("=" * 60)

        return result

    def _process_file(self, file_path: str, dry_run: bool, result: TaskResult):
        """
        Process a single invoice file.

        Args:
            file_path: Path to file to process
            dry_run: Dry run mode
            result: TaskResult to update
        """
        path = Path(file_path)
        logger.info(f"\nProcessing: {path.name}")

        # Check if already processed
        if self.db.is_processed(path.name):
            logger.info(f"Already processed, skipping: {path.name}")
            result.skipped += 1
            return

        # OCR recognition
        logger.info("  -> Running OCR...")
        ocr_result = self.ocr_engine.recognize_auto(str(path))

        if not ocr_result.text:
            logger.warning(f"  -> OCR produced no text, skipping")
            result.failed += 1
            result.errors.append(f"{path.name}: No text recognized")
            return

        logger.info(f"  -> OCR confidence: {ocr_result.confidence:.2f}")

        # Parse invoice information
        logger.info("  -> Parsing invoice...")
        info = self.parser.parse(ocr_result, raw_filename=path.name)

        if info.confidence < self.config.ocr.confidence_threshold:
            logger.warning(f"  -> Low confidence ({info.confidence:.2f}), may need review")

        # Generate new filename
        logger.info("  -> Generating new filename...")
        ext = self.renamer.get_extension(str(path))
        new_filename = self.renamer.generate_name(info, ext)

        # Handle conflicts
        target_dir = self.organizer.get_target_path(info)
        new_filename = self.renamer.make_unique(new_filename, target_dir)

        logger.info(f"  -> New filename: {new_filename}")

        # Organize file
        logger.info("  -> Organizing file...")
        if dry_run:
            final_path = self.organizer.organize(
                str(path),
                info,
                new_filename,
                dry_run=True
            )
        else:
            final_path = self.organizer.organize(
                str(path),
                info,
                new_filename,
                dry_run=False
            )

        if final_path:
            # Record in database
            record = ProcessedRecord(
                remote_path=path.name,
                local_path=str(path),
                final_path=str(final_path),
                invoice_type=info.type.value,
                invoice_date=info.date.isoformat() if info.date else None,
                amount=float(info.amount) if info.amount else None,
                traveler=info.traveler,
                status=ProcessStatus.SUCCESS.value,
                raw_ocr_text=ocr_result.text[:1000],  # Store first 1000 chars
            )
            self.db.add_record(record)

            logger.info(f"  -> Success: {new_filename}")
            result.success += 1
        else:
            result.failed += 1
            result.errors.append(f"{path.name}: Failed to organize file")

    def _cleanup_temp(self, file_paths: List[str]):
        """
        Clean up temporary files.

        Args:
            file_paths: List of file paths to clean up
        """
        for file_path in file_paths:
            path = Path(file_path)
            try:
                if path.exists():
                    path.unlink()
                    logger.debug(f"Cleaned up: {path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup {path}: {e}")

    def start_daily(self, hour: Optional[int] = None, minute: Optional[int] = None):
        """
        Start daily scheduled task.

        Args:
            hour: Hour to run (default from config)
            minute: Minute to run (default from config)
        """
        if hour is None:
            hour = self.config.scheduler.daily_hour
        if minute is None:
            minute = self.config.scheduler.daily_minute

        logger.info(f"Starting daily scheduler at {hour:02d}:{minute:02d}")

        self.scheduler = BlockingScheduler()

        # Add daily job
        self.scheduler.add_job(
            self._scheduled_run,
            trigger=CronTrigger(hour=hour, minute=minute),
            id='daily_invoice_process',
            name='Daily Invoice Processing',
            replace_existing=True
        )

        # Log next run time
        next_run = self.scheduler.get_job('daily_invoice_process').next_run_time
        logger.info(f"Next run scheduled at: {next_run}")

        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped")

    def _scheduled_run(self):
        """Wrapper for scheduled job."""
        logger.info("Running scheduled task...")
        try:
            result = self.run_once()
            logger.info(f"Scheduled task completed: {result}")
        except Exception as e:
            logger.error(f"Scheduled task failed: {e}")

    def get_statistics(self) -> dict:
        """
        Get processing statistics from database.

        Returns:
            Dict with statistics
        """
        self.db.connect()
        try:
            stats = self.db.get_statistics()
            return stats
        finally:
            self.db.close()

    def get_recent_records(self, limit: int = 20) -> List[ProcessedRecord]:
        """
        Get recently processed records.

        Args:
            limit: Maximum number of records

        Returns:
            List of recent records
        """
        self.db.connect()
        try:
            return self.db.get_recent_records(limit)
        finally:
            self.db.close()

    def get_failed_records(self) -> List[ProcessedRecord]:
        """
        Get failed processing records.

        Returns:
            List of failed records
        """
        self.db.connect()
        try:
            return self.db.get_failed_records()
        finally:
            self.db.close()
