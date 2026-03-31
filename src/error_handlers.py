"""
Error handling and retry logic for the invoice processing system.

Provides:
- Retry decorators for network operations
- Fallback strategies for OCR failures
- Manual review queue for failed files
- Error recovery mechanisms
"""

import time
import functools
from pathlib import Path
from typing import Callable, Optional, Any, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from loguru import logger


class ErrorType(Enum):
    """Types of errors that can occur."""
    OCR_FAILURE = "ocr_failure"
    PARSE_FAILURE = "parse_failure"
    NETWORK_ERROR = "network_error"
    FILE_ERROR = "file_error"
    UNKNOWN = "unknown"


@dataclass
class FailedFile:
    """Record of a file that failed processing."""
    file_path: str
    error_type: ErrorType
    error_message: str
    timestamp: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    resolved: bool = False
    notes: str = ""


class RetryPolicy:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0
    ):
        """
        Initialize retry policy.

        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Initial delay between retries in seconds
            max_delay: Maximum delay between retries
            backoff_factor: Multiplier for delay after each retry
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor


def retry_on_error(
    error_types: tuple = (Exception,),
    policy: Optional[RetryPolicy] = None
):
    """
    Decorator to retry function on specific errors.

    Args:
        error_types: Tuple of exception types to catch
        policy: RetryPolicy instance (uses default if None)

    Returns:
        Decorated function with retry logic
    """
    if policy is None:
        policy = RetryPolicy()

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_error = None
            delay = policy.base_delay

            for attempt in range(policy.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except error_types as e:
                    last_error = e
                    if attempt < policy.max_retries:
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{policy.max_retries}): {e}"
                        )
                        logger.info(f"Retrying in {delay:.1f} seconds...")
                        time.sleep(delay)
                        delay = min(delay * policy.backoff_factor, policy.max_delay)
                    else:
                        logger.error(f"{func.__name__} failed after {policy.max_retries} retries: {e}")

            raise last_error

        return wrapper
    return decorator


class ManualReviewQueue:
    """Queue for files that require manual review."""

    def __init__(self, queue_file: str = "data/manual_review.json"):
        """
        Initialize manual review queue.

        Args:
            queue_file: Path to JSON file storing the queue
        """
        self.queue_file = Path(queue_file)
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        self.failed_files: List[FailedFile] = []
        self._load_queue()

    def _load_queue(self):
        """Load queue from JSON file."""
        import json

        if self.queue_file.exists():
            try:
                with open(self.queue_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.failed_files = [
                        FailedFile(
                            file_path=item['file_path'],
                            error_type=ErrorType(item['error_type']),
                            error_message=item['error_message'],
                            timestamp=datetime.fromisoformat(item['timestamp']),
                            retry_count=item.get('retry_count', 0),
                            resolved=item.get('resolved', False),
                            notes=item.get('notes', '')
                        )
                        for item in data
                    ]
                logger.info(f"Loaded {len(self.failed_files)} items from manual review queue")
            except Exception as e:
                logger.error(f"Failed to load manual review queue: {e}")
                self.failed_files = []

    def _save_queue(self):
        """Save queue to JSON file."""
        import json

        try:
            data = [
                {
                    'file_path': f.file_path,
                    'error_type': f.error_type.value,
                    'error_message': f.error_message,
                    'timestamp': f.timestamp.isoformat(),
                    'retry_count': f.retry_count,
                    'resolved': f.resolved,
                    'notes': f.notes
                }
                for f in self.failed_files if not f.resolved  # Only save unresolved
            ]
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"Saved {len(data)} items to manual review queue")
        except Exception as e:
            logger.error(f"Failed to save manual review queue: {e}")

    def add_failure(
        self,
        file_path: str,
        error_type: ErrorType,
        error_message: str
    ):
        """
        Add a failed file to the queue.

        Args:
            file_path: Path to the failed file
            error_type: Type of error that occurred
            error_message: Error message
        """
        # Check if already in queue
        for existing in self.failed_files:
            if existing.file_path == file_path and not existing.resolved:
                existing.retry_count += 1
                existing.timestamp = datetime.now()
                logger.warning(f"Updated retry count for {file_path}: {existing.retry_count}")
                self._save_queue()
                return

        # Add new failure
        failed_file = FailedFile(
            file_path=file_path,
            error_type=error_type,
            error_message=error_message
        )
        self.failed_files.append(failed_file)
        logger.warning(f"Added {file_path} to manual review queue: {error_type.value}")
        self._save_queue()

    def mark_resolved(self, file_path: str, notes: str = ""):
        """
        Mark a file as resolved.

        Args:
            file_path: Path to the resolved file
            notes: Optional notes about resolution
        """
        for failed_file in self.failed_files:
            if failed_file.file_path == file_path:
                failed_file.resolved = True
                failed_file.notes = notes
                logger.info(f"Marked {file_path} as resolved: {notes}")
                self._save_queue()
                return

        logger.warning(f"File not found in queue: {file_path}")

    def get_pending(self) -> List[FailedFile]:
        """
        Get list of pending files for review.

        Returns:
            List of unresolved FailedFile objects
        """
        return [f for f in self.failed_files if not f.resolved]

    def get_statistics(self) -> dict:
        """
        Get queue statistics.

        Returns:
            Dict with queue statistics
        """
        pending = self.get_pending()
        resolved = [f for f in self.failed_files if f.resolved]

        # Count by error type
        error_counts = {}
        for f in pending:
            error_counts[f.error_type.value] = error_counts.get(f.error_type.value, 0) + 1

        return {
            'total_pending': len(pending),
            'total_resolved': len(resolved),
            'by_error_type': error_counts,
            'average_retries': sum(f.retry_count for f in pending) / len(pending) if pending else 0
        }


class OCRFallbackHandler:
    """Handler for OCR recognition failures."""

    @staticmethod
    def try_alternative_ocr(file_path: str) -> Optional[str]:
        """
        Try alternative OCR methods when primary OCR fails.

        Args:
            file_path: Path to the file

        Returns:
            OCR text if successful, None otherwise
        """
        path = Path(file_path)

        # Try with different preprocessing
        try:
            from .ocr_engine import get_ocr_engine
            ocr = get_ocr_engine()

            # Try with grayscale enhancement
            result = ocr.recognize_auto(str(path), enhance=True)
            if result.text:
                logger.info(f"OCR with enhancement succeeded for {path.name}")
                return result.text

        except Exception as e:
            logger.warning(f"Enhanced OCR failed: {e}")

        return None

    @staticmethod
    def suggest_manual_review(file_path: str) -> str:
        """
        Suggest file needs manual review.

        Args:
            file_path: Path to the file

        Returns:
            Suggested action message
        """
        return f"OCR failed for {Path(file_path).name}. Please check if file is readable and consider manual entry."


class ParseFallbackHandler:
    """Handler for parsing failures."""

    @staticmethod
    def extract_basic_info(text: str) -> dict:
        """
        Extract basic information from OCR text when full parsing fails.

        Args:
            text: OCR text

        Returns:
            Dict with basic extracted information
        """
        import re

        info = {
            'raw_text': text,
            'amount': None,
            'date': None,
            'type': None
        }

        # Try to extract amount (look for currency patterns)
        amount_patterns = [
            r'¥?\s*(\d+\.?\d*)\s*元',
            r'(\d+\.\d{2})',
            r'金额[：:]\s*(\d+\.?\d*)'
        ]
        for pattern in amount_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    info['amount'] = float(match.group(1))
                    break
                except (ValueError, IndexError):
                    pass

        # Try to extract date
        date_patterns = [
            r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})',
            r'(\d{4})-(\d{2})-(\d{2})'
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    year, month, day = match.groups()
                    info['date'] = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    break
                except (ValueError, IndexError):
                    pass

        return info

    @staticmethod
    def suggest_manual_entry(file_path: str, text: str) -> str:
        """
        Suggest manual entry for failed parse.

        Args:
            file_path: Path to the file
            text: OCR text

        Returns:
            Suggested action message
        """
        basic_info = ParseFallbackHandler.extract_basic_info(text)

        message = f"Parse failed for {Path(file_path).name}. "
        if basic_info['amount']:
            message += f"Detected amount: {basic_info['amount']}元. "
        if basic_info['date']:
            message += f"Detected date: {basic_info['date']}. "
        message += "Please enter invoice details manually."

        return message


# Global review queue instance
_review_queue = None


def get_review_queue() -> ManualReviewQueue:
    """Get the global manual review queue instance."""
    global _review_queue
    if _review_queue is None:
        _review_queue = ManualReviewQueue()
    return _review_queue
