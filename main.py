#!/usr/bin/env python
"""
Main entry point for the invoice organizer application.

Usage:
    python main.py --run           # Run once
    python main.py --daily         # Start daily scheduler
    python main.py --dry-run       # Simulate run without moving files
    python main.py --stats         # Show statistics
    python main.py --recent        # Show recent records
    python main.py --failed        # Show failed records
"""

import sys
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger

from src.config import get_config, setup_logging
from src.scheduler import TaskScheduler


def cmd_run(args):
    """Run invoice processing once."""
    scheduler = TaskScheduler()
    result = scheduler.run_once(dry_run=args.dry_run)

    # Exit with error code if any failures
    if result.failed > 0:
        sys.exit(1)


def cmd_daily(args):
    """Start daily scheduler."""
    scheduler = TaskScheduler()
    scheduler.start_daily(hour=args.hour, minute=args.minute)


def cmd_stats(args):
    """Show processing statistics."""
    scheduler = TaskScheduler()
    stats = scheduler.get_statistics()

    print("\n" + "=" * 50)
    print("INVOICE PROCESSING STATISTICS")
    print("=" * 50)

    print(f"\nTotal Records: {stats['total']}")
    print(f"  Success: {stats['success']}")
    print(f"  Failed:  {stats['failed']}")
    print(f"  Skipped: {stats['skipped']}")

    if stats['by_type']:
        print("\nBy Invoice Type:")
        for invoice_type, count in sorted(stats['by_type'].items(), key=lambda x: -x[1]):
            print(f"  {invoice_type}: {count}")

    if stats['by_traveler']:
        print("\nBy Traveler:")
        for traveler, count in sorted(stats['by_traveler'].items(), key=lambda x: -x[1]):
            print(f"  {traveler}: {count}")

    print("\n" + "=" * 50 + "\n")


def cmd_recent(args):
    """Show recently processed records."""
    scheduler = TaskScheduler()
    records = scheduler.get_recent_records(limit=args.limit)

    if not records:
        print("No recent records found.")
        return

    print(f"\nRecent {len(records)} records:")
    print("-" * 80)

    for record in records:
        status_icon = "✓" if record.status == "success" else "✗"
        print(f"\n[{status_icon}] {record.final_path or record.remote_path}")
        print(f"  Type: {record.invoice_type or 'Unknown'}")
        print(f"  Date: {record.invoice_date or 'Unknown'}")
        print(f"  Amount: {record.amount or 0:.2f}")
        print(f"  Traveler: {record.traveler or 'Unknown'}")
        print(f"  Processed: {record.processed_at}")

        if record.error_message:
            print(f"  Error: {record.error_message}")

    print("\n" + "-" * 80 + "\n")


def cmd_failed(args):
    """Show failed processing records."""
    scheduler = TaskScheduler()
    records = scheduler.get_failed_records()

    if not records:
        print("No failed records found.")
        return

    print(f"\nFailed records ({len(records)}):")
    print("-" * 80)

    for record in records:
        print(f"\n[✗] {record.remote_path}")
        print(f"  Error: {record.error_message or 'Unknown error'}")
        print(f"  Processed: {record.processed_at}")

    print("\n" + "-" * 80 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="出差发票自动整理系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --run              Run processing once
  python main.py --dry-run          Simulate run without moving files
  python main.py --daily            Start daily scheduler (runs at configured time)
  python main.py --daily --hour 3   Start scheduler with custom time (3:00 AM)
  python main.py --stats            Show processing statistics
  python main.py --recent           Show recent records
  python main.py --failed           Show failed records
        """
    )

    parser.add_argument(
        "--config", "-c",
        help="Path to configuration file"
    )

    # Mode selection (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--run",
        action="store_true",
        help="Run invoice processing once"
    )
    mode_group.add_argument(
        "--daily",
        action="store_true",
        help="Start daily scheduler"
    )
    mode_group.add_argument(
        "--stats",
        action="store_true",
        help="Show processing statistics"
    )
    mode_group.add_argument(
        "--recent",
        action="store_true",
        help="Show recently processed records"
    )
    mode_group.add_argument(
        "--failed",
        action="store_true",
        help="Show failed processing records"
    )

    # Optional arguments
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate run without actually moving files"
    )
    parser.add_argument(
        "--hour", "-H",
        type=int,
        default=None,
        help="Hour for daily scheduler (0-23)"
    )
    parser.add_argument(
        "--minute", "-M",
        type=int,
        default=None,
        help="Minute for daily scheduler (0-59)"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=20,
        help="Limit number of records to show (default: 20)"
    )

    args = parser.parse_args()

    # Setup logging
    config = get_config()
    setup_logging(config.logging)

    # Execute command
    try:
        if args.run:
            cmd_run(args)
        elif args.daily:
            cmd_daily(args)
        elif args.stats:
            cmd_stats(args)
        elif args.recent:
            cmd_recent(args)
        elif args.failed:
            cmd_failed(args)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
