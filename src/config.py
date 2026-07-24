"""
Configuration management module for invoice organizer.

Handles loading and accessing configuration from YAML files.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import time

import yaml
from loguru import logger


@dataclass
class BaiduPanConfig:
    """Baidu Pan (bypy) configuration"""
    remote_dir: str = "invoices"
    temp_dir: str = "temp"
    process_after_download: bool = True


@dataclass
class EmailConfig:
    """Email (IMAP) configuration for downloading invoice attachments"""
    # IMAP server settings
    imap_server: str = "imap.zju.edu.cn"
    imap_port: int = 993
    mailbox: str = "INBOX"

    # Authentication
    email_address: str = ""
    authorization_code: str = ""

    # Sync settings
    temp_dir: str = "temp"
    check_days: int = 30  # Check emails from last N days
    max_emails: int = 200  # Max emails to retrieve per sync

    # Filter settings - sender keywords (domains or email patterns)
    sender_keywords: List[str] = field(default_factory=list)
    # Filter settings - subject keywords
    subject_keywords: List[str] = field(default_factory=list)
    # Allowed attachment extensions
    attachment_extensions: List[str] = field(default_factory=lambda: ['.pdf', '.jpg', '.png'])

    # Processing options
    mark_as_read: bool = True  # Mark emails as read after processing
    delete_after_download: bool = False  # Not recommended


@dataclass
class OcrConfig:
    """OCR engine configuration"""
    use_angle_cls: bool = True
    lang: str = "ch"
    use_gpu: bool = False
    confidence_threshold: float = 0.6


@dataclass
class SchedulerConfig:
    """Task scheduler configuration"""
    daily_hour: int = 2
    daily_minute: int = 0
    timeout: int = 3600


@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    file: str = "logs/invoice_organizer.log"
    retention_days: int = 30
    max_size_mb: int = 100


@dataclass
class OptionsConfig:
    """Processing options"""
    delete_temp_after_process: bool = True
    skip_existing: bool = True
    dry_run: bool = False


@dataclass
class Config:
    """Main configuration class"""
    baidu_pan: BaiduPanConfig = field(default_factory=BaiduPanConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    local_output_dir: str = "invoices"
    default_traveler: str = "张三"
    options: OptionsConfig = field(default_factory=OptionsConfig)
    ocr: OcrConfig = field(default_factory=OcrConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Project root directory
    _project_root: Optional[Path] = field(default=None, init=False, repr=False)

    @classmethod
    def from_yaml(cls, config_path: str = "config/config.yaml") -> "Config":
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to configuration file

        Returns:
            Config: Loaded configuration instance
        """
        config_file = Path(config_path)

        if not config_file.exists():
            logger.warning(f"Config file not found: {config_path}, using defaults")
            return cls()

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            # Create nested configs
            baidu_pan = BaiduPanConfig(**data.get("baidu_pan", {}))
            email = EmailConfig(**data.get("email", {}))
            options = OptionsConfig(**data.get("options", {}))
            ocr = OcrConfig(**data.get("ocr", {}))
            scheduler = SchedulerConfig(**data.get("scheduler", {}))
            logging = LoggingConfig(**data.get("logging", {}))

            # Create main config
            config = cls(
                baidu_pan=baidu_pan,
                email=email,
                local_output_dir=data.get("local_output_dir", "invoices"),
                default_traveler=data.get("default_traveler", "张三"),
                options=options,
                ocr=ocr,
                scheduler=scheduler,
                logging=logging,
            )

            # Set project root
            config._project_root = config_file.parent.parent

            logger.info(f"Configuration loaded from: {config_path}")
            return config

        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            logger.warning("Using default configuration")
            return cls()

    @property
    def project_root(self) -> Path:
        """Get project root directory."""
        if self._project_root is None:
            # Default to current working directory
            self._project_root = Path.cwd()
        return self._project_root

    def get_temp_dir(self) -> Path:
        """Get absolute path to temporary directory."""
        return self.project_root / self.temp_dir

    def get_output_dir(self) -> Path:
        """Get absolute path to output directory."""
        return self.project_root / self.local_output_dir

    def get_log_dir(self) -> Path:
        """Get absolute path to log directory."""
        return self.project_root / "logs"

    def get_data_dir(self) -> Path:
        """Get absolute path to data directory."""
        return self.project_root / "data"

    def get_config_dir(self) -> Path:
        """Get absolute path to config directory."""
        return self.project_root / "config"

    def get_db_path(self) -> Path:
        """Get absolute path to SQLite database."""
        return self.get_data_dir() / "records.db"


class ParserConfig:
    """Invoice parser rules configuration."""

    def __init__(self, config_path: str = "config/parsers.yaml"):
        """
        Load parser configuration.

        Args:
            config_path: Path to parsers.yaml file
        """
        self.config_path = Path(config_path)
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self):
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            logger.warning(f"Parser config not found: {self.config_path}")
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}
            logger.info(f"Parser config loaded: {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to load parser config: {e}")

    @property
    def type_detection(self) -> Dict[str, Dict[str, Any]]:
        """Get type detection rules."""
        return self._data.get("type_detection", {})

    @property
    def field_extraction(self) -> Dict[str, List[Dict[str, str]]]:
        """Get field extraction rules."""
        return self._data.get("field_extraction", {})

    @property
    def naming_templates(self) -> Dict[str, str]:
        """Get naming templates."""
        return self._data.get("naming_templates", {})

    @property
    def defaults(self) -> Dict[str, Any]:
        """Get default values."""
        return self._data.get("defaults", {})


class TravelerConfig:
    """Traveler information configuration."""

    def __init__(self, config_path: str = "config/travelers.yaml"):
        """
        Load traveler configuration.

        Args:
            config_path: Path to travelers.yaml file
        """
        self.config_path = Path(config_path)
        self._data: Dict[str, Any] = {}
        self._traveler_map: Dict[str, str] = {}
        self._load()

    def _load(self):
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            logger.warning(f"Traveler config not found: {self.config_path}")
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}

            # Build traveler name mapping (aliases -> standard name)
            default = self._data.get("default", "张三")
            travelers = self._data.get("travelers", [])

            # Add default to map
            self._traveler_map[default] = default

            for traveler in travelers:
                name = traveler.get("name", "")
                aliases = traveler.get("aliases", [])
                self._traveler_map[name] = name
                for alias in aliases:
                    self._traveler_map[alias] = name

            logger.info(f"Traveler config loaded: {len(self._traveler_map)} entries")
        except Exception as e:
            logger.error(f"Failed to load traveler config: {e}")

    @property
    def default(self) -> str:
        """Get default traveler name."""
        return self._data.get("default", "张三")

    def normalize_name(self, name: str) -> str:
        """
        Normalize traveler name to standard form.

        Args:
            name: Raw traveler name

        Returns:
            str: Standardized traveler name
        """
        if not name:
            return self.default

        # Check if name is already in map
        if name in self._traveler_map:
            return self._traveler_map[name]

        # Try case-insensitive match
        name_lower = name.lower()
        for alias, standard in self._traveler_map.items():
            if alias.lower() == name_lower:
                return standard

        # Return original if not found
        return name

    def get_all_travelers(self) -> List[str]:
        """Get list of all unique traveler names."""
        return list(set(self._traveler_map.values()))


class BuyerConfig:
    """Buyer (发票购买方/抬头) configuration, keyed by tax_id.

    Used to classify invoices by buyer company. Lookup is by tax_id
    (统一社会信用代码), which OCR recognizes far more reliably than
    Chinese company names.
    """

    def __init__(self, config_path: str = "config/buyers.yaml"):
        """
        Load buyer configuration.

        Args:
            config_path: Path to buyers.yaml file
        """
        self.config_path = Path(config_path)
        self._data: Dict[str, Any] = {}
        self._buyer_map: Dict[str, Dict[str, str]] = {}  # tax_id(upper) -> {full_name, dir_name}
        self._default: str = "未分类"
        self._load()

    def _load(self):
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            logger.warning(f"Buyer config not found: {self.config_path}")
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._data = yaml.safe_load(f) or {}

            self._default = self._data.get("default", "未分类")

            for buyer in self._data.get("buyers", []):
                tax_id = (buyer.get("tax_id") or "").strip().upper()
                if not tax_id:
                    continue
                self._buyer_map[tax_id] = {
                    "full_name": buyer.get("full_name", ""),
                    "dir_name": buyer.get("dir_name", "") or self._default,
                    "default_traveler": buyer.get("default_traveler"),
                }

            logger.info(f"Buyer config loaded: {len(self._buyer_map)} entries")
        except Exception as e:
            logger.error(f"Failed to load buyer config: {e}")

    @property
    def default(self) -> str:
        """Get default dir name for unrecognized buyers."""
        return self._default

    def lookup_by_taxid(self, tax_id: str) -> Optional[Dict[str, str]]:
        """
        Look up buyer info by tax_id.

        Returns:
            Dict with 'full_name' and 'dir_name', or None if not found.
        """
        if not tax_id:
            return None
        return self._buyer_map.get(tax_id.strip().upper())

    def get_dir_name(self, tax_id: str) -> str:
        """Get directory name for a tax_id (falls back to default)."""
        info = self.lookup_by_taxid(tax_id)
        return info["dir_name"] if info else self._default

    def get_full_name(self, tax_id: str) -> Optional[str]:
        """Get full company name for a tax_id (None if not found)."""
        info = self.lookup_by_taxid(tax_id)
        return info["full_name"] if info else None

    def get_default_traveler(self, tax_id: str) -> Optional[str]:
        """
        Get the default traveler for a buyer (None if not configured).

        Used when an invoice has no recognizable real traveler name — e.g.
        星辰基石 flights whose cabin class ("经济舱") gets mis-read as a name.
        """
        info = self.lookup_by_taxid(tax_id)
        return info.get("default_traveler") if info else None

    def get_all_tax_ids(self) -> List[str]:
        """Get list of all configured tax_ids (upper-cased)."""
        return list(self._buyer_map.keys())

    def find_taxid_by_name(self, text: str) -> Optional[str]:
        """
        Find a buyer whose full_name appears in text. Returns its tax_id.

        Used as a fallback when the tax id itself is OCR-corrupted (e.g. a
        dropped digit). Returns None if no configured company name is found.

        Args:
            text: Full OCR text (case-sensitive Chinese match)

        Returns:
            Matching tax_id (upper-cased) or None
        """
        if not text:
            return None
        for tax_id, info in self._buyer_map.items():
            name = info.get("full_name", "")
            if name and name in text:
                return tax_id
        return None


# Global configuration instance
_config: Optional[Config] = None
_parser_config: Optional[ParserConfig] = None
_traveler_config: Optional[TravelerConfig] = None
_buyer_config: Optional[BuyerConfig] = None


def get_config(reload: bool = False) -> Config:
    """
    Get global configuration instance.

    Args:
        reload: Force reload configuration

    Returns:
        Config: Configuration instance
    """
    global _config
    if _config is None or reload:
        _config = Config.from_yaml()
    return _config


def get_parser_config(reload: bool = False) -> ParserConfig:
    """
    Get global parser configuration instance.

    Args:
        reload: Force reload configuration

    Returns:
        ParserConfig: Parser configuration instance
    """
    global _parser_config
    if _parser_config is None or reload:
        _parser_config = ParserConfig()
    return _parser_config


def get_traveler_config(reload: bool = False) -> TravelerConfig:
    """
    Get global traveler configuration instance.

    Args:
        reload: Force reload configuration

    Returns:
        TravelerConfig: Traveler configuration instance
    """
    global _traveler_config
    if _traveler_config is None or reload:
        _traveler_config = TravelerConfig()
    return _traveler_config


def get_buyer_config(reload: bool = False) -> BuyerConfig:
    """
    Get global buyer configuration instance.

    Args:
        reload: Force reload configuration

    Returns:
        BuyerConfig: Buyer configuration instance
    """
    global _buyer_config
    if _buyer_config is None or reload:
        _buyer_config = BuyerConfig()
    return _buyer_config


def setup_logging(config: Optional[LoggingConfig] = None):
    """
    Setup logging configuration with enhanced features.

    Args:
        config: Logging configuration (uses global config if None)
    """
    if config is None:
        config = get_config().logging

    # Remove default handler
    logger.remove()

    # Create logs directory
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # Add console handler with colors
    logger.add(
        sink=lambda msg: print(msg, end=""),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=config.level,
        colorize=True,
    )

    # Add general log file with daily rotation
    logger.add(
        sink=log_dir / "invoice_{time:YYYY-MM-DD}.log",
        rotation="00:00",  # Rotate at midnight
        retention="30 days",
        compression="zip",
        level="DEBUG",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )

    # Add error log file (separate from general log)
    logger.add(
        sink=log_dir / "errors_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="90 days",  # Keep error logs longer
        compression="zip",
        level="ERROR",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )

    logger.info("Logging initialized with daily rotation and error tracking")
