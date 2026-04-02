"""
Task scheduler module for automated invoice processing.

Orchestrates the complete invoice processing workflow.
"""

import time
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from loguru import logger

from .config import get_config, setup_logging
from .database import RecordDatabase, ProcessedRecord, ProcessStatus
from .bypy_sync import BypySyncManager
from .email_sync import EmailSyncManager
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

    # Email/Baidu sync stats
    emails_processed: int = 0
    files_downloaded: int = 0
    files_processed: int = 0

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
    1. Sync new files from Email (IMAP) or Baidu Pan
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

        # Choose sync manager based on config
        # If email address is configured, use EmailSyncManager
        if hasattr(self.config, 'email') and self.config.email.email_address:
            self.sync_manager = EmailSyncManager()
            logger.info("Using Email Sync Manager")
        else:
            self.sync_manager = BypySyncManager()
            logger.info("Using Baidu Pan Sync Manager")

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

            # Step 2: Sync new files from source (Email or Baidu Pan)
            logger.info("Step 1: Syncing new files...")
            # Pass database to EmailSyncManager for proper email UID tracking
            new_files = self.sync_manager.sync_new_files(known_files, db=self.db)
            logger.info(f"Found {len(new_files)} new files")

            if not new_files:
                logger.info("No new files to process")
                result.end_time = datetime.now()
                return result

            result.total = len(new_files)
            result.files_downloaded = len(new_files)

            # Step 3: Group files by email for cross-referencing
            logger.info("Step 2: Grouping files by email...")
            files_by_email = self._group_files_by_email(new_files)
            result.emails_processed = len(files_by_email)

            # Step 4: Process files in email groups
            logger.info("Step 3: Processing files...")
            for email_uid, file_list in files_by_email.items():
                # Process bills first to extract dates, then invoices
                self._process_email_group(file_list, dry_run, result)

            # Update files_processed count
            result.files_processed = result.success

            # Step 5: Cleanup temp files
            if self.config.options.delete_temp_after_process and not dry_run:
                logger.info("Cleaning up temp directory...")
                self._cleanup_temp(new_files)

            # Step 6: Match car invoices with trip receipts
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

        # Log summary with statistics and alerts
        logger.info("=" * 60)
        logger.info(f"Task completed: {result}")

        # Log detailed statistics
        if result.success > 0 or result.failed > 0:
            logger.info(f"Processed: {result.success} succeeded, {result.failed} failed, {result.skipped} skipped")
            if result.duration:
                logger.info(f"Duration: {result.duration:.1f} seconds")

        # Log error alerts if needed
        from .logging_config import ErrorAlertManager
        alert_manager = ErrorAlertManager()
        alerts = alert_manager.check_errors(result)
        if alerts:
            alert_manager.log_alerts(alerts)

        logger.info("=" * 60)

        return result

    def _process_file(self, file_path: str, dry_run: bool, result: TaskResult, bill_dates: Optional[dict] = None, trip_receipt_types: Optional[dict] = None):
        """
        Process a single invoice file.

        Args:
            file_path: Path to file to process
            dry_run: Dry run mode
            result: TaskResult to update
            bill_dates: Optional dict of bill dates from same email
            trip_receipt_types: Optional dict mapping trip receipt amounts to {'type': InvoiceType, 'date': date}
        """
        from .parser import InvoiceType
        from .error_handlers import ErrorType, get_review_queue, OCRFallbackHandler, ParseFallbackHandler

        path = Path(file_path)
        logger.info(f"\nProcessing: {path.name}")

        # Check if already processed - use email_uid + filename if available
        is_processed = False
        if hasattr(self.sync_manager, 'downloaded_files_meta'):
            # Check if this file has email metadata
            email_meta = self.sync_manager.downloaded_files_meta.get(file_path)
            if not email_meta:
                email_meta = self.sync_manager.downloaded_files_meta.get(file_path.replace('\\', '/'))

            if email_meta:
                # Use email_uid + filename combination for accurate check
                is_processed = self.db.is_processed_by_email(str(email_meta.uid), path.name)
            else:
                # Fallback to filename-only check for non-email files
                is_processed = self.db.is_processed(path.name)
        else:
            # No email metadata available, use filename check
            is_processed = self.db.is_processed(path.name)

        if is_processed:
            logger.info(f"Already processed, skipping: {path.name}")
            result.skipped += 1
            return

        # OCR recognition with fallback
        logger.info("  -> Running OCR...")
        try:
            ocr_result = self.ocr_engine.recognize_auto(str(path))
        except Exception as e:
            logger.warning(f"  -> OCR error: {e}")
            # Try fallback
            fallback_text = OCRFallbackHandler.try_alternative_ocr(str(path))
            if fallback_text:
                from .ocr_engine import OCRResult
                ocr_result = OCRResult(text=fallback_text, confidence=0.5)
            else:
                # Add to review queue
                review_queue = get_review_queue()
                review_queue.add_failure(
                    str(path),
                    ErrorType.OCR_FAILURE,
                    f"OCR failed: {str(e)}"
                )
                result.failed += 1
                result.errors.append(f"{path.name}: OCR failure - {OCRFallbackHandler.suggest_manual_review(str(path))}")
                return

        if not ocr_result.text:
            logger.warning(f"  -> OCR produced no text, skipping")
            # Add to review queue
            review_queue = get_review_queue()
            review_queue.add_failure(
                str(path),
                ErrorType.OCR_FAILURE,
                "No text recognized"
            )
            result.failed += 1
            result.errors.append(f"{path.name}: No text recognized")
            return

        logger.info(f"  -> OCR confidence: {ocr_result.confidence:.2f}")

        # Parse invoice information with fallback
        logger.info("  -> Parsing invoice...")
        try:
            info = self.parser.parse(ocr_result, raw_filename=path.name)
        except Exception as e:
            logger.warning(f"  -> Parse error: {e}")
            # Try fallback extraction
            basic_info = ParseFallbackHandler.extract_basic_info(ocr_result.text)
            if basic_info.get('amount') or basic_info.get('date'):
                # Create minimal InvoiceInfo from basic info
                from .parser import InvoiceInfo, InvoiceType
                info = InvoiceInfo(
                    type=InvoiceType.OTHER,
                    amount=basic_info.get('amount'),
                    date_str=basic_info.get('date'),
                    raw_text=ocr_result.text
                )
                logger.info(f"  -> Fallback extraction succeeded: amount={info.amount}, date={info.date}")
            else:
                # Add to review queue
                review_queue = get_review_queue()
                review_queue.add_failure(
                    str(path),
                    ErrorType.PARSE_FAILURE,
                    f"Parse failed: {str(e)}"
                )
                result.failed += 1
                result.errors.append(f"{path.name}: {ParseFallbackHandler.suggest_manual_entry(str(path), ocr_result.text)}")
                return

        # Check if this is an invoice (发票, not 行程单) for transportation
        is_transport_invoice = (
            not info.is_trip_receipt and
            info.type in [InvoiceType.TAXI, InvoiceType.AIRPORT_TRANSFER, InvoiceType.AIRPLANE, InvoiceType.TRAIN]
        )

        # For transportation invoices, check if there's a matching trip receipt
        if is_transport_invoice and trip_receipt_types and info.amount:
            amount_key = float(info.amount)
            if amount_key in trip_receipt_types:
                receipt_info = trip_receipt_types[amount_key]
                receipt_type = receipt_info['type']
                receipt_date = receipt_info['date']
                receipt_start_date = receipt_info.get('trip_start_date')
                receipt_end_date = receipt_info.get('trip_end_date')

                # Update type to match trip receipt
                if info.type != receipt_type:
                    logger.info(f"  -> Matching trip receipt type is {receipt_type.value}, updating invoice type")
                    info.type = receipt_type

                # Use trip receipt date range for taxi and airport transfer invoices
                if info.type in [InvoiceType.TAXI, InvoiceType.AIRPORT_TRANSFER]:
                    if receipt_start_date and receipt_end_date:
                        info.trip_start_date = receipt_start_date
                        info.trip_end_date = receipt_end_date
                        info.date = receipt_start_date
                        logger.info(f"  -> Using trip receipt date range: {receipt_start_date} to {receipt_end_date}")
                    elif not info.date and receipt_date:
                        info.date = receipt_date
                        logger.info(f"  -> Using trip receipt date: {receipt_date}")
                elif not info.date and receipt_date:
                    info.date = receipt_date
                    logger.info(f"  -> Using trip receipt date: {receipt_date}")

        # For hotel invoices without stay dates, use dates from bill if available
        if info.type == InvoiceType.HOTEL and bill_dates:
            if not info.check_in_date or not info.check_out_date:
                # Use dates from any bill in the same email
                for check_in, check_out in bill_dates.values():
                    info.check_in_date = check_in
                    info.check_out_date = check_out
                    # Also update the invoice date
                    info.date = check_in
                    logger.info(f"  -> Using dates from bill: {check_in} to {check_out}")
                    break

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
            # Determine remote_path - use relative path from temp/ for email files
            remote_path = path.name
            if hasattr(self.sync_manager, 'temp_dir') and path.is_relative_to(self.sync_manager.temp_dir):
                # For files from email sync, use relative path from temp/ to ensure uniqueness
                remote_path = str(path.relative_to(self.sync_manager.temp_dir))

            # Record in database
            record = ProcessedRecord(
                remote_path=remote_path,
                local_path=str(path),
                final_path=str(final_path),
                invoice_type=info.type.value,
                invoice_date=info.date.isoformat() if info.date else None,
                amount=float(info.amount) if info.amount else None,
                traveler=info.traveler,
                status=ProcessStatus.SUCCESS.value,
                raw_ocr_text=ocr_result.text[:1000],  # Store first 1000 chars
            )

            # Add email metadata if available (for EmailSyncManager)
            if hasattr(self.sync_manager, 'downloaded_files_meta'):
                # Try both forward and back slashes for path matching
                email_meta = self.sync_manager.downloaded_files_meta.get(str(path))
                if not email_meta:
                    # Try with backslashes
                    email_meta = self.sync_manager.downloaded_files_meta.get(str(path).replace('/', '\\'))
                if not email_meta:
                    # Try with forward slashes
                    email_meta = self.sync_manager.downloaded_files_meta.get(str(path).replace('\\', '/'))
                if email_meta:
                    record.source_type = 'email'
                    record.email_uid = email_meta.uid
                    record.email_subject = email_meta.subject
                    record.email_sender = email_meta.sender
                    record.email_date = email_meta.date
                    record.attachment_name = path.name

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

    def _group_files_by_email(self, file_paths: List[str]) -> Dict[str, List[str]]:
        """
        Group files by email UID for cross-referencing.

        Args:
            file_paths: List of file paths

        Returns:
            Dict mapping email UID to list of file paths
        """
        from .parser import InvoiceInfo

        files_by_email = {}

        # Check if sync manager has email metadata
        if hasattr(self.sync_manager, 'downloaded_files_meta'):
            for file_path in file_paths:
                # Try both forward and back slashes for path matching
                email_meta = self.sync_manager.downloaded_files_meta.get(file_path)
                if not email_meta:
                    email_meta = self.sync_manager.downloaded_files_meta.get(file_path.replace('\\', '/'))
                if not email_meta:
                    email_meta = self.sync_manager.downloaded_files_meta.get(file_path.replace('/', '\\'))

                if email_meta:
                    uid = email_meta.uid
                    if uid not in files_by_email:
                        files_by_email[uid] = []
                    files_by_email[uid].append(file_path)
                else:
                    # No email metadata, process individually
                    uid = f"individual_{file_path}"
                    files_by_email[uid] = [file_path]
        else:
            # No email metadata, process all individually
            for file_path in file_paths:
                uid = f"individual_{file_path}"
                files_by_email[uid] = [file_path]

        return files_by_email

    def _process_email_group(self, file_paths: List[str], dry_run: bool, result: TaskResult):
        """
        Process a group of files from the same email.

        Bills are processed first to extract dates, then invoices use those dates.
        Trip receipts (行程单) are processed to determine types for matching invoices.

        Args:
            file_paths: List of file paths from the same email
            dry_run: Dry run mode
            result: TaskResult to update
        """
        from .parser import InvoiceType, InvoiceInfo

        # First pass: identify bills and extract their dates
        bill_dates = {}  # Maps file_path -> (check_in, check_out)

        # Track trip receipt types by amount for matching invoices
        # Maps amount -> InvoiceType (e.g., 133.00 -> AIRPORT_TRANSFER)
        trip_receipt_types = {}

        for file_path in file_paths:
            try:
                path = Path(file_path)
                if not path.exists():
                    continue

                # Quick check: if filename contains "结账单" or "账单"
                if "结账单" in path.name or "账单" in path.name:
                    # OCR and parse to extract dates
                    try:
                        ocr_result = self.ocr_engine.recognize_auto(str(path))
                        if ocr_result.text:
                            info = self.parser.parse(ocr_result, raw_filename=path.name)
                            if info.check_in_date and info.check_out_date:
                                bill_dates[file_path] = (info.check_in_date, info.check_out_date)
                                logger.info(f"  -> Extracted dates from bill: {info.check_in_date} to {info.check_out_date}")
                    except Exception as e:
                        logger.debug(f"  -> Failed to extract dates from {path.name}: {e}")

                # Check for trip receipts (行程单) to determine types and dates for invoices
                elif "行程单" in path.name:
                    try:
                        ocr_result = self.ocr_engine.recognize_auto(str(path))
                        if ocr_result.text:
                            info = self.parser.parse(ocr_result, raw_filename=path.name)
                            if info.amount and info.is_trip_receipt:
                                # Store type, date range by amount for matching invoices
                                trip_receipt_types[float(info.amount)] = {
                                    'type': info.type,
                                    'date': info.date,
                                    'trip_start_date': info.trip_start_date,
                                    'trip_end_date': info.trip_end_date,
                                }
                                logger.info(f"  -> Trip receipt: type={info.type.value}, amount={info.amount}, date={info.date}, trip_range={info.trip_start_date}至{info.trip_end_date}")
                    except Exception as e:
                        logger.debug(f"  -> Failed to parse trip receipt {path.name}: {e}")
            except Exception as e:
                logger.debug(f"  -> Error checking file {file_path}: {e}")

        # Second pass: process all files
        for file_path in file_paths:
            try:
                self._process_file(file_path, dry_run, result, bill_dates=bill_dates, trip_receipt_types=trip_receipt_types)
            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")
                result.failed += 1
                result.errors.append(f"{file_path}: {str(e)}")

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
