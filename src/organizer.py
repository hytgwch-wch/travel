"""
Invoice file organizer module.

Organizes processed files into categorized directory structure.
"""

import shutil
from pathlib import Path
from typing import Optional, Dict
from datetime import date

from loguru import logger

from .parser import InvoiceInfo, InvoiceType
from .config import get_config


class InvoiceOrganizer:
    """
    Organize invoice files into categorized directory structure.

    Directory structure:
        invoices/
        ├── {year}/
        │   ├── {month}/
        │   │   ├── 交通/    (机票, 火车, 打车)
        │   │   ├── 住宿/    (酒店)
        │   │   ├── 餐饮/    (餐饮)
        │   │   └── 其他/    (其他类型)
    """

    # Type to category mapping
    TYPE_CATEGORIES: Dict[InvoiceType, str] = {
        InvoiceType.AIRPLANE: "交通",
        InvoiceType.AIRPORT_TRANSFER: "交通",
        InvoiceType.TRAIN: "交通",
        InvoiceType.TAXI: "交通",
        InvoiceType.HOTEL: "住宿",
        InvoiceType.BILL: "住宿",  # Bills go to hotel category
        InvoiceType.DINING: "餐饮",
        InvoiceType.CAR_RENTAL: "其他",
        InvoiceType.OTHER: "其他",
    }

    def __init__(self):
        """Initialize organizer."""
        self.config = get_config()
        self.base_dir = Path(self.config.local_output_dir)

    def get_target_path(self, info: InvoiceInfo) -> Path:
        """
        Calculate target directory path for invoice.

        Args:
            info: Parsed invoice information

        Returns:
            Path: Target directory path
        """
        # Get year
        if info.date:
            year = info.date.year
        else:
            # Use current date if not available
            today = date.today()
            year = today.year

        # Get category
        category = self.TYPE_CATEGORIES.get(info.type, "其他")

        # Build path: invoices/{year}/{category}/
        target_path = self.base_dir / str(year) / category

        return target_path

    def organize(
        self,
        source_path: str,
        info: InvoiceInfo,
        new_filename: str,
        dry_run: bool = False
    ) -> Optional[Path]:
        """
        Organize file to target directory.

        Args:
            source_path: Source file path
            info: Parsed invoice information
            new_filename: New filename for the file
            dry_run: If True, simulate without actually moving

        Returns:
            Path: Final file path (or would-be path if dry_run)
        """
        source = Path(source_path)
        if not source.exists():
            logger.error(f"Source file not found: {source_path}")
            return None

        # Get target directory
        target_dir = self.get_target_path(info)

        # Create target directory
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
        else:
            logger.debug(f"[DRY RUN] Would create directory: {target_dir}")

        # Target file path
        target_path = target_dir / new_filename

        # Handle file conflicts
        if target_path.exists():
            logger.warning(f"Target file exists: {target_path}")
            # Add timestamp suffix
            stem = target_path.stem
            ext = target_path.suffix
            from datetime import datetime
            timestamp = datetime.now().strftime("%H%M%S")
            target_path = target_dir / f"{stem}_{timestamp}{ext}"
            logger.info(f"Using alternative name: {target_path.name}")

        # Move/copy file
        if not dry_run:
            try:
                shutil.move(str(source), str(target_path))
                logger.info(f"Moved: {source} -> {target_path}")
            except Exception as e:
                logger.error(f"Failed to move file: {e}")
                # Try copy as fallback
                try:
                    shutil.copy2(str(source), str(target_path))
                    logger.info(f"Copied: {source} -> {target_path}")
                except Exception as e2:
                    logger.error(f"Failed to copy file: {e2}")
                    return None
        else:
            logger.info(f"[DRY RUN] Would move: {source} -> {target_path}")

        return target_path

    def copy_file(
        self,
        source_path: str,
        info: InvoiceInfo,
        new_filename: str,
        dry_run: bool = False
    ) -> Optional[Path]:
        """
        Copy file to target directory (instead of moving).

        Args:
            source_path: Source file path
            info: Parsed invoice information
            new_filename: New filename for the file
            dry_run: If True, simulate without actually copying

        Returns:
            Path: Final file path (or would-be path if dry_run)
        """
        source = Path(source_path)
        if not source.exists():
            logger.error(f"Source file not found: {source_path}")
            return None

        # Get target directory
        target_dir = self.get_target_path(info)

        # Create target directory
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
        else:
            logger.debug(f"[DRY RUN] Would create directory: {target_dir}")

        # Target file path
        target_path = target_dir / new_filename

        # Handle file conflicts
        if target_path.exists():
            logger.warning(f"Target file exists: {target_path}")
            stem = target_path.stem
            ext = target_path.suffix
            from datetime import datetime
            timestamp = datetime.now().strftime("%H%M%S")
            target_path = target_dir / f"{stem}_{timestamp}{ext}"
            logger.info(f"Using alternative name: {target_path.name}")

        # Copy file
        if not dry_run:
            try:
                shutil.copy2(str(source), str(target_path))
                logger.info(f"Copied: {source} -> {target_path}")
            except Exception as e:
                logger.error(f"Failed to copy file: {e}")
                return None
        else:
            logger.info(f"[DRY RUN] Would copy: {source} -> {target_path}")

        return target_path

    def get_category_stats(self) -> Dict[str, int]:
        """
        Get statistics of files in each category.

        Returns:
            Dict mapping category paths to file counts
        """
        stats = {}

        if not self.base_dir.exists():
            return stats

        for year_dir in self.base_dir.iterdir():
            if not year_dir.is_dir():
                continue

            for month_dir in year_dir.iterdir():
                if not month_dir.is_dir():
                    continue

                for category_dir in month_dir.iterdir():
                    if not category_dir.is_dir():
                        continue

                    # Count files
                    file_count = sum(1 for _ in category_dir.iterdir() if _.is_file())
                    stats[str(category_dir)] = file_count

        return stats

    def ensure_structure(self, dry_run: bool = False):
        """
        Ensure directory structure exists.

        Creates all necessary directories for current year/month.

        Args:
            dry_run: If True, simulate without creating
        """
        today = date.today()
        year = str(today.year)
        month = f"{today.month:02d}"

        categories = set(self.TYPE_CATEGORIES.values())

        for category in categories:
            path = self.base_dir / year / month / category
            if not dry_run:
                path.mkdir(parents=True, exist_ok=True)
                logger.debug(f"Created directory: {path}")
            else:
                logger.debug(f"[DRY RUN] Would create: {path}")
