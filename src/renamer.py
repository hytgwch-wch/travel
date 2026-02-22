"""
Invoice file renamer module.

Generates standardized filenames based on invoice information.
"""

import re
import string
from pathlib import Path
from typing import Optional

from loguru import logger


# Control characters (ASCII 0-31, 127)
CONTROL_CHARS = set(chr(i) for i in range(32)) | {chr(127)}

from .parser import InvoiceInfo, InvoiceType


class InvoiceRenamer:
    """
    Generate standardized filenames for invoices.

    Naming format: {date}_{type}_{details}_{amount}_{traveler}.ext
    """

    # Invalid filename characters (Windows)
    INVALID_CHARS = '<>:"/\\|?*'
    INVALID_CHARS_REPLACE = '__________'

    def __init__(self):
        """Initialize renamer."""
        pass

    def generate_name(self, info: InvoiceInfo, original_ext: str = ".pdf") -> str:
        """
        Generate standardized filename from invoice info.

        Args:
            info: Parsed invoice information
            original_ext: Original file extension (default: .pdf)

        Returns:
            str: Generated filename (without directory path)
        """
        # Get extension
        ext = original_ext if original_ext.startswith('.') else f'.{original_ext}'

        # Format date
        date_str = ""
        if info.date:
            date_str = info.date.strftime("%Y-%m-%d")
        else:
            date_str = "unknown_date"

        # Format amount
        amount_str = ""
        if info.amount:
            amount_str = f"{info.amount:.2f}"
        else:
            amount_str = "0.00"

        # Generate name based on invoice type
        name_parts = self._get_name_parts(info)
        base_name = "_".join(filter(None, [date_str] + name_parts + [amount_str, info.traveler or "unknown"]))

        # Add document type suffix for certain types
        if info.type == InvoiceType.AIRPORT_TRANSFER:
            # 接送机: 有路线信息的是行程单，没有的是发票
            if info.origin and info.destination:
                # Trip receipt - has route info
                base_name += "_行程单"
            else:
                # Car invoice - no route info
                base_name += "_发票"

        # Clean up name
        base_name = self._sanitize_filename(base_name)

        # Combine with extension
        return f"{base_name}{ext}"

    def _get_name_parts(self, info: InvoiceInfo) -> list[str]:
        """Get name parts based on invoice type."""
        type_mapping = {
            InvoiceType.AIRPLANE: ["机票"],
            InvoiceType.AIRPORT_TRANSFER: ["接送机"],
            InvoiceType.TRAIN: ["火车"],
            InvoiceType.TAXI: ["打车"],
            InvoiceType.HOTEL: ["住宿"],
            InvoiceType.DINING: ["餐饮"],
            InvoiceType.CAR_RENTAL: ["租车"],
            InvoiceType.OTHER: ["其他"],
        }

        type_part = type_mapping.get(info.type, ["其他"])

        if info.type == InvoiceType.AIRPLANE:
            # 机票: {类型}_{起点}_{终点}
            return type_part + [info.origin or "", info.destination or ""]

        elif info.type == InvoiceType.AIRPORT_TRANSFER:
            # 接送机行程单: {类型}_{起点}_{终点}
            # Note: "_行程单" suffix will be added in the main name
            return type_part + [info.origin or "", info.destination or ""]

        elif info.type == InvoiceType.TRAIN:
            # 火车: {类型}_{起点}_{终点}
            return type_part + [info.origin or "", info.destination or ""]

        elif info.type == InvoiceType.TAXI:
            # 打车: {类型}_{起点}_{终点}
            return type_part + [info.origin or "", info.destination or ""]

        elif info.type == InvoiceType.HOTEL:
            # 住宿: {类型}_{城市}_{酒店名}
            return type_part + [info.city or "", info.hotel_name or ""]

        elif info.type == InvoiceType.DINING:
            # 餐饮: {类型}_{城市}
            return type_part + [info.city or ""]

        elif info.type == InvoiceType.CAR_RENTAL:
            # 租车: {类型}_{城市}_{天数}天
            days_str = f"{info.stay_days}天" if info.stay_days else ""
            return type_part + [info.city or "", days_str]

        else:
            # 其他: {类型}_{子类型}
            return type_part

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename by removing/replacing invalid characters.

        Args:
            filename: Raw filename

        Returns:
            str: Sanitized filename
        """
        # Replace invalid characters with underscore
        for char in self.INVALID_CHARS:
            filename = filename.replace(char, '_')

        # Remove control characters
        filename = ''.join(char for char in filename if char not in CONTROL_CHARS)

        # Remove extra whitespace
        filename = re.sub(r'\s+', '_', filename)

        # Remove consecutive underscores
        filename = re.sub(r'_+', '_', filename)

        # Strip leading/trailing underscores and dots
        filename = filename.strip('._')

        # Limit length (Windows has 260 char limit, keep safe)
        if len(filename) > 200:
            # Preserve extension
            parts = filename.rsplit('.', 1)
            if len(parts) == 2:
                base, ext = parts
                filename = base[:200 - len(ext) - 1] + '.' + ext
            else:
                filename = filename[:200]

        return filename

    def make_unique(self, base_name: str, output_dir: Path) -> str:
        """
        Ensure filename is unique in output directory.

        Adds numeric suffix if file already exists.

        Args:
            base_name: Proposed filename
            output_dir: Output directory path

        Returns:
            str: Unique filename
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Split name and extension
        parts = base_name.rsplit('.', 1)
        if len(parts) == 2:
            name_base, ext = parts
            full_name = f"{name_base}.{ext}"
        else:
            name_base = parts[0]
            ext = ""
            full_name = name_base

        # Check if file exists
        target_path = output_dir / full_name
        if not target_path.exists():
            return full_name

        # Add numeric suffix
        counter = 1
        while True:
            new_name = f"{name_base}_{counter}"
            if ext:
                new_name = f"{new_name}.{ext}"

            if not (output_dir / new_name).exists():
                logger.info(f"File exists, using unique name: {new_name}")
                return new_name

            counter += 1
            if counter > 1000:
                # Safety limit
                raise RuntimeError(f"Too many file conflicts for: {base_name}")

    def get_extension(self, file_path: str) -> str:
        """
        Get file extension from path.

        Args:
            file_path: File path

        Returns:
            str: File extension (with dot, lowercase)
        """
        return Path(file_path).suffix.lower()
