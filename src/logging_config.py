"""
Logging configuration module for the invoice processing system.

Configures loguru logger with:
- Console output with colors
- File output with daily rotation
- Separate error log file
- Structured logging format
"""

import sys
from pathlib import Path
from loguru import logger
from datetime import datetime


class LogConfig:
    """Centralized logging configuration."""

    def __init__(self, log_dir: Path = None):
        """
        Initialize logging configuration.

        Args:
            log_dir: Directory for log files (default: logs/)
        """
        self.log_dir = log_dir or Path("logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Remove default handler
        logger.remove()

        # Configure console handler
        self._add_console_handler()

        # Configure file handlers
        self._add_file_handlers()

    def _add_console_handler(self):
        """Add console logging handler with colors."""
        logger.add(
            sys.stderr,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level="INFO",
            colorize=True,
        )

    def _add_file_handlers(self):
        """Add file logging handlers with rotation."""
        # General log file - rotated daily
        logger.add(
            self.log_dir / "invoice_{time:YYYY-MM-DD}.log",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="DEBUG",
            rotation="00:00",  # Rotate at midnight
            retention="30 days",  # Keep logs for 30 days
            compression="zip",  # Compress old logs
            encoding="utf-8",
        )

        # Error log file - for errors only
        logger.add(
            self.log_dir / "errors_{time:YYYY-MM-DD}.log",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="ERROR",
            rotation="00:00",
            retention="90 days",  # Keep error logs longer
            compression="zip",
            encoding="utf-8",
        )

    @staticmethod
    def get_logger():
        """Get the configured logger instance."""
        return logger


class StatisticsLogger:
    """Logger for processing statistics and metrics."""

    def __init__(self, db):
        """
        Initialize statistics logger.

        Args:
            db: RecordDatabase instance for statistics
        """
        self.db = db

    def log_daily_summary(self):
        """Log daily processing summary."""
        stats = self.db.get_statistics()

        logger.info("=" * 60)
        logger.info("每日处理统计")
        logger.info("=" * 60)
        logger.info(f"总处理文件数: {stats['total']}")
        logger.info(f"成功: {stats['success']}")
        logger.info(f"失败: {stats['failed']}")
        logger.info(f"跳过: {stats['skipped']}")

        if stats['by_type']:
            logger.info("\n按类型统计:")
            for invoice_type, count in stats['by_type'].items():
                logger.info(f"  {invoice_type}: {count}")

        if stats['by_traveler']:
            logger.info("\n按出差人统计:")
            for traveler, count in stats['by_traveler'].items():
                logger.info(f"  {traveler}: {count}")

        logger.info("=" * 60)

    def log_task_result(self, result):
        """
        Log task execution result.

        Args:
            result: TaskResult object
        """
        logger.info(f"任务完成 - 总计: {result.total}, 成功: {result.success}, 失败: {result.failed}, 跳过: {result.skipped}")

        if result.duration:
            logger.info(f"耗时: {result.duration:.1f}秒")

        if result.errors:
            logger.warning(f"错误数量: {len(result.errors)}")
            for error in result.errors[:5]:  # Show first 5 errors
                logger.error(f"  - {error}")

    def log_monthly_summary(self, months: int = 12):
        """
        Log monthly processing summary.

        Args:
            months: Number of months to include
        """
        stats = self.db.get_monthly_stats(months)

        logger.info("=" * 60)
        logger.info(f"最近 {months} 个月统计")
        logger.info("=" * 60)

        for stat in stats:
            logger.info(f"{stat['month']}: {stat['count']} 个文件, 总金额: {stat['total_amount']:.2f} 元")

        logger.info("=" * 60)


class ErrorAlertManager:
    """Manager for error alerts and notifications."""

    def __init__(self, error_threshold: int = 5):
        """
        Initialize error alert manager.

        Args:
            error_threshold: Number of errors before triggering alert
        """
        self.error_threshold = error_threshold
        self.error_count = 0
        self.last_alert_time = None

    def check_errors(self, result) -> list:
        """
        Check if error alert should be triggered.

        Args:
            result: TaskResult object

        Returns:
            List of alert messages
        """
        alerts = []

        # Check error count
        if result.failed >= self.error_threshold:
            alerts.append(f"⚠️ 错误数量过高: {result.failed} 个文件处理失败")

        # Check error rate
        if result.total > 0:
            error_rate = result.failed / result.total
            if error_rate > 0.2:  # More than 20% error rate
                alerts.append(f"⚠️ 错误率过高: {error_rate*100:.1f}%")

        # Check for specific error patterns
        for error in result.errors:
            if "OCR" in str(error).upper():
                alerts.append(f"⚠️ OCR 识别错误: {error}")
            elif "网络" in str(error) or "连接" in str(error):
                alerts.append(f"⚠️ 网络连接错误: {error}")
            elif "解析" in str(error):
                alerts.append(f"⚠️ 发票解析错误: {error}")

        return alerts

    def log_alerts(self, alerts: list):
        """
        Log alert messages.

        Args:
            alerts: List of alert messages
        """
        if alerts:
            logger.warning("=" * 60)
            logger.warning("⚠️ 错误告警")
            logger.warning("=" * 60)
            for alert in alerts:
                logger.warning(alert)
            logger.warning("=" * 60)


def setup_logging(log_dir: Path = None) -> tuple:
    """
    Set up logging system for the application.

    Args:
        log_dir: Directory for log files

    Returns:
        Tuple of (logger, statistics_logger, error_alert_manager)
    """
    # Configure loguru
    log_config = LogConfig(log_dir)

    # Create components
    stats_logger = None  # Will be initialized with DB
    alert_manager = ErrorAlertManager()

    return logger, stats_logger, alert_manager
