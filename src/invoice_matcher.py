"""
Invoice matcher module.

Matches car invoices with their corresponding trip receipts for airport transfers and taxi rides.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional
from loguru import logger


class InvoiceMatcher:
    """
    Match car invoices with trip receipts for airport transfers and taxi rides.

    Trip receipts and car invoices are one-to-one correspondences.
    They can be matched by amount.

    Handles multiple receipts/invoices with the same amount by tracking which ones are matched.
    """

    def __init__(self, base_dir: str = "invoices"):
        """Initialize matcher."""
        self.base_dir = Path(base_dir)

    def match_and_rename_invoices(self) -> int:
        """
        Find all taxi invoices and match them with trip receipts, then rename.

        Uses trip receipt's date instead of invoice date.

        Returns:
            int: Number of invoices renamed
        """
        # Build indexes of trip receipts and invoices
        trip_receipts = self._index_trip_receipts()
        invoices_to_match = self._index_invoices_to_match()

        if not trip_receipts:
            logger.info("No trip receipts found for matching")
            return 0

        total_receipts = sum(len(receipts) for receipts in trip_receipts.values())
        logger.info(f"Found {total_receipts} trip receipts for matching")

        # Match invoices with trip receipts
        renamed_count = 0
        matched_receipts = set()  # Track which receipts are matched

        for amount, invoice_list in invoices_to_match.items():
            if amount not in trip_receipts:
                logger.debug(f"No matching trip receipt for amount {amount}")
                continue

            receipt_list = trip_receipts[amount]

            # Match invoices with receipts (1-to-1)
            for i, invoice_info in enumerate(invoice_list):
                # Find an unmatched receipt for this amount
                for j, receipt_info in enumerate(receipt_list):
                    receipt_key = (amount, receipt_info['filename'])

                    if receipt_key in matched_receipts:
                        continue  # This receipt is already matched

                    # Match them
                    new_name = f"{receipt_info['date']}_打车_{receipt_info['amount_str']}_{invoice_info['traveler']}_发票.pdf"
                    old_path = invoice_info['path']
                    new_path = old_path.parent / new_name

                    if new_name != invoice_info['filename']:
                        try:
                            if new_path.exists():
                                logger.warning(f"Target already exists, skipping: {invoice_info['filename']} -> {new_name}")
                                continue

                            old_path.rename(new_path)
                            renamed_count += 1
                            matched_receipts.add(receipt_key)
                            logger.info(f"Matched: {invoice_info['filename']} -> {new_name}")
                        except Exception as e:
                            logger.error(f"Failed to rename {invoice_info['filename']}: {e}")

                    break  # Move to next invoice

        logger.info(f"Matched and renamed {renamed_count} taxi invoices")
        return renamed_count

    def _index_trip_receipts(self) -> Dict[float, List[Dict]]:
        """
        Build an index of trip receipts by amount.

        Returns:
            Dict mapping amount to list of trip receipt info
        """
        trip_receipts: Dict[float, List[Dict]] = {}

        for root, dirs, files in os.walk(str(self.base_dir)):
            for filename in files:
                if '_行程单.pdf' in filename and '_打车_' in filename:
                    match = re.match(
                        r'((?:\d{4}-\d{2}-\d{2}(?:至|至)\d{4}-\d{2}-\d{2}|\d{4}-\d{2}-\d{2}))_打车_(\d+\.\d{2})_(.+?)_行程单\.pdf$',
                        filename
                    )

                    if match:
                        date_str, amount_str, traveler = match.groups()
                        amount = float(amount_str)

                        if amount not in trip_receipts:
                            trip_receipts[amount] = []

                        trip_receipts[amount].append({
                            'file': Path(root) / filename,
                            'filename': filename,
                            'date': date_str,
                            'amount_str': amount_str,
                            'traveler': traveler
                        })
                        logger.debug(f"Indexed trip receipt: {filename} -> amount={amount}, date_range={date_str}")

        return trip_receipts

    def _index_invoices_to_match(self) -> Dict[float, List[Dict]]:
        """
        Build an index of invoices that need matching (single date format).

        Returns:
            Dict mapping amount to list of invoice info
        """
        invoices: Dict[float, List[Dict]] = {}

        for root, dirs, files in os.walk(str(self.base_dir)):
            for filename in files:
                if '_发票' in filename and '_打车_' in filename:
                    # Skip if already has date range format
                    first_part = filename.split('_')[0]
                    if '至' in first_part:
                        continue  # Already matched

                    # Pattern matches:
                    # - 2026-03-28_打车_36.00_王春晖_发票.pdf
                    # - 2026-03-28_打车_36.00_王春晖_发票_1.pdf (duplicate)
                    # The suffix _1, _2, etc. may come before or after _发票
                    match = re.match(
                        r'(\d{4}-\d{2}-\d{2})_打车_(\d+\.\d{2})_(.+?)(?:_\d+)?_发票(?:_\d+)?\.pdf$',
                        filename
                    )

                    if match:
                        date_str, amount_str, traveler = match.groups()
                        amount = float(amount_str)

                        if amount not in invoices:
                            invoices[amount] = []

                        invoices[amount].append({
                            'path': Path(root) / filename,
                            'filename': filename,
                            'invoice_date': date_str,
                            'traveler': traveler
                        })

        return invoices


def match_invoices(base_dir: str = "invoices") -> int:
    """
    Convenience function to match and rename invoices.

    Args:
        base_dir: Base directory containing invoices

    Returns:
        int: Number of invoices renamed
    """
    matcher = InvoiceMatcher(base_dir)
    return matcher.match_and_rename_invoices()
