"""
Invoice matcher module.

Matches car invoices with their corresponding trip receipts for airport transfers.
"""

import re
from pathlib import Path
from typing import Dict, Optional
from loguru import logger


class InvoiceMatcher:
    """
    Match car invoices with trip receipts for airport transfers.

    Trip receipts and car invoices are one-to-one correspondences.
    They can be matched by amount.
    """

    def __init__(self, base_dir: str = "invoices"):
        """Initialize matcher."""
        self.base_dir = Path(base_dir)

    def match_and_rename_invoices(self) -> int:
        """
        Find all car invoices and match them with trip receipts, then rename.

        Returns:
            int: Number of invoices renamed
        """
        # Build index of trip receipts by amount
        trip_receipts = self._index_trip_receipts()

        if not trip_receipts:
            logger.info("No trip receipts found for matching")
            return 0

        logger.info(f"Found {len(trip_receipts)} trip receipts for matching")

        # Find and match car invoices
        renamed_count = 0

        for f in self.base_dir.rglob('*_打车_*.pdf'):
            # Parse the taxi invoice filename
            # Format: 2026-02-20_打车_125.00_王春晖.pdf or 2026-02-20_打车_125.00_王春晖_1.pdf
            match = re.match(r'(\d{4}-\d{2}-\d{2})_打车_(\d+\.\d{2})_(.+?)(?:_\d+)?\.pdf$', f.name)

            if match:
                invoice_date, amount_str, traveler = match.groups()
                amount = float(amount_str)

                # Find matching trip receipt by amount
                if amount in trip_receipts:
                    trip_info = trip_receipts[amount]

                    # Use traveler from trip receipt (stripping any _N suffix)
                    receipt_traveler = trip_info["traveler"].split('_')[0]

                    # Generate new filename with route info from trip receipt
                    # Format: {invoice_date}_接送机_{route}_{amount}_{traveler}_发票.pdf
                    new_name = f'{invoice_date}_接送机_{trip_info["route"]}_{amount_str}_{receipt_traveler}_发票.pdf'
                    new_path = f.parent / new_name

                    # Rename the file
                    try:
                        f.rename(new_path)
                        renamed_count += 1
                        logger.info(f"Matched and renamed: {new_name}")
                    except Exception as e:
                        logger.error(f"Failed to rename {f.name}: {e}")
                else:
                    logger.debug(f"No matching trip receipt for amount {amount}")

        logger.info(f"Matched and renamed {renamed_count} car invoices")
        return renamed_count

    def _index_trip_receipts(self) -> Dict[float, Dict]:
        """
        Build an index of trip receipts by amount.

        Returns:
            Dict mapping amount to trip receipt info
        """
        trip_receipts = {}

        for f in self.base_dir.rglob('*_接送机_*_行程单.pdf'):
            # Parse trip receipt filename
            # Format: 2026-02-10_接送机_逸城-北门_萧山国际机场_T3_151.00_王春晖_行程单.pdf
            match = re.match(
                r'(\d{4}-\d{2}-\d{2})_接送机_(.+?)_(\d+\.\d{2})_(.+?)_行程单\.pdf$',
                f.name
            )

            if match:
                date_str, route, amount_str, traveler = match.groups()
                amount = float(amount_str)

                trip_receipts[amount] = {
                    'file': f,
                    'date': date_str,
                    'route': route,
                    'amount_str': amount_str,
                    'traveler': traveler
                }

        return trip_receipts


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
