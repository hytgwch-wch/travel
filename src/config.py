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
            options = OptionsConfig(**data.get("options", {}))
            ocr = OcrConfig(**data.get("ocr", {}))
            scheduler = SchedulerConfig(**data.get("scheduler", {}))
            logging = LoggingConfig(**data.get("logging", {}))

            # Create main config
            config = cls(
                baidu_pan=baidu_pan,
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


# Global configuration instance
_config: Optional[Config] = None
_parser_config: Optional[ParserConfig] = None
_traveler_config: Optional[TravelerConfig] = None


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


def setup_logging(config: Optional[LoggingConfig] = None):
    """
    Setup logging configuration.

    Args:
        config: Logging configuration (uses global config if None)
    """
    if config is None:
        config = get_config().logging

    # Remove default handler
    logger.remove()

    # Add console handler
    logger.add(
        sink=lambda msg: print(msg, end=""),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=config.level,
    )

    # Add file handler
    log_file = Path(config.file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        sink=config.file,
        rotation=f"{config.max_size_mb} MB",
        retention=f"{config.retention_days} days",
        level=config.level,
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )

    logger.info("Logging initialized")
