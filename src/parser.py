"""
Invoice parser module.

Extracts structured information from OCR text results.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Optional, List, Dict, Any
from decimal import Decimal

from loguru import logger

from .config import get_parser_config, get_traveler_config
from .ocr_engine import OCRResult


class InvoiceType(Enum):
    """Invoice type enumeration"""
    AIRPLANE = "机票"
    AIRPORT_TRANSFER = "接送机"
    TRAIN = "火车"
    TAXI = "打车"
    HOTEL = "住宿"
    DINING = "餐饮"
    CAR_RENTAL = "租车"
    OTHER = "其他"


@dataclass
class InvoiceInfo:
    """Structured invoice information"""
    # Basic info
    type: InvoiceType
    date: Optional[date] = None
    amount: Optional[Decimal] = None

    # Travel info
    traveler: Optional[str] = None

    # Transport specific
    origin: Optional[str] = None
    destination: Optional[str] = None
    transport_mode: Optional[str] = None

    # Hotel specific
    city: Optional[str] = None
    hotel_name: Optional[str] = None
    stay_days: Optional[int] = None

    # Other
    raw_name: Optional[str] = None
    confidence: float = 0.0

    def __str__(self) -> str:
        return f"InvoiceInfo(type={self.type.value}, date={self.date}, amount={self.amount}, traveler={self.traveler})"


class InvoiceParser:
    """
    Parse invoice information from OCR text.

    Uses configurable rules to extract structured data.
    """

    def __init__(self):
        """Initialize parser with configuration."""
        self.parser_config = get_parser_config()
        self.traveler_config = get_traveler_config()

        # Compile regex patterns from config
        self._patterns = self._compile_patterns()

    def _compile_patterns(self) -> Dict[str, List[re.Pattern]]:
        """Compile regex patterns from config."""
        patterns = {}

        field_extraction = self.parser_config.field_extraction

        for field_name, rules in field_extraction.items():
            compiled = []
            for rule in rules:
                pattern_str = rule.get("pattern", "")
                try:
                    compiled.append(re.compile(pattern_str))
                except re.error as e:
                    logger.warning(f"Invalid regex for {field_name}: {pattern_str} - {e}")
            patterns[field_name] = compiled

        return patterns

    def parse(self, ocr_result: OCRResult, raw_filename: Optional[str] = None) -> InvoiceInfo:
        """
        Parse invoice information from OCR result.

        Args:
            ocr_result: OCR recognition result
            raw_filename: Original filename (for reference)

        Returns:
            InvoiceInfo: Parsed invoice information
        """
        text = ocr_result.text
        lines = ocr_result.lines

        # Detect invoice type
        invoice_type = self.detect_type(ocr_result)

        # Extract common fields
        invoice_date = self._extract_date(text)
        amount = self._extract_amount(text)
        traveler = self._extract_traveler(text)

        # Normalize traveler name
        if traveler:
            traveler = self.traveler_config.normalize_name(traveler)
        else:
            traveler = self.traveler_config.default

        # Create base info
        info = InvoiceInfo(
            type=invoice_type,
            date=invoice_date,
            amount=amount,
            traveler=traveler,
            raw_name=raw_filename,
            confidence=ocr_result.confidence
        )

        # Extract type-specific fields
        if invoice_type == InvoiceType.AIRPLANE:
            info.origin, info.destination = self._extract_airplane_route(text)
            info.transport_mode = "飞机"

        elif invoice_type == InvoiceType.AIRPORT_TRANSFER:
            info.origin, info.destination = self._extract_airport_transfer_route(text)
            info.transport_mode = "接送机"

        elif invoice_type == InvoiceType.TRAIN:
            info.origin, info.destination = self._extract_train_route(text)
            info.transport_mode = "火车"

        elif invoice_type == InvoiceType.TAXI:
            info.origin, info.destination = self._extract_taxi_route(text)
            info.transport_mode = "打车/网约车"

        elif invoice_type == InvoiceType.HOTEL:
            info.city, info.hotel_name = self._extract_hotel_info(text)
            info.stay_days = self._extract_stay_days(text)

        elif invoice_type == InvoiceType.DINING:
            info.city = self._extract_city(text)

        elif invoice_type == InvoiceType.CAR_RENTAL:
            info.city = self._extract_city(text)
            info.stay_days = self._extract_stay_days(text)
            info.transport_mode = "租车"

        logger.info(f"Parsed invoice: {info}")
        return info

    def detect_type(self, ocr_result: OCRResult) -> InvoiceType:
        """
        Detect invoice type from OCR text.

        Args:
            ocr_result: OCR recognition result

        Returns:
            InvoiceType: Detected invoice type
        """
        text = ocr_result.text
        lines = ocr_result.lines

        type_detection = self.parser_config.type_detection

        # Score each invoice type
        scores = {}

        for invoice_type, config in type_detection.items():
            keywords = config.get("keywords", [])
            priority = config.get("priority", 0)

            score = 0
            for keyword in keywords:
                if keyword in text:
                    score += 1

            if score > 0:
                scores[invoice_type] = score * 100 + priority

        # Find highest scoring type
        if not scores:
            logger.debug("No invoice type detected, defaulting to OTHER")
            return InvoiceType.OTHER

        detected_type = max(scores, key=scores.get)

        # Map string to enum
        type_mapping = {
            "airplane": InvoiceType.AIRPLANE,
            "airport_transfer": InvoiceType.AIRPORT_TRANSFER,
            "train": InvoiceType.TRAIN,
            "taxi": InvoiceType.TAXI,
            "hotel": InvoiceType.HOTEL,
            "dining": InvoiceType.DINING,
            "car_rental": InvoiceType.CAR_RENTAL,
            "other": InvoiceType.OTHER,
        }

        return type_mapping.get(detected_type, InvoiceType.OTHER)

    def _extract_date(self, text: str) -> Optional[date]:
        """Extract date from text."""
        patterns = self._patterns.get("date", [])

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                try:
                    groups = match.groups()
                    if len(groups) >= 3:
                        year, month, day = groups[0], groups[1], groups[2]
                        # Handle zero-padding
                        month = month.zfill(2)
                        day = day.zfill(2)
                        return datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d").date()
                except ValueError:
                    continue

        return None

    def _extract_amount(self, text: str) -> Optional[Decimal]:
        """Extract amount from text."""
        patterns = self._patterns.get("amount", [])

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                try:
                    amount_str = match.group(1).replace(",", "")
                    return Decimal(amount_str)
                except (ValueError, IndexError):
                    continue

        return None

    def _extract_traveler(self, text: str) -> Optional[str]:
        """Extract traveler name from text."""
        patterns = self._patterns.get("traveler", [])

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                try:
                    name = match.group(1).strip()
                    if name and len(name) >= 2 and len(name) <= 10:
                        return name
                except IndexError:
                    continue

        return None

    def _extract_city(self, text: str) -> Optional[str]:
        """Extract city name from text."""
        # Common Chinese city pattern
        city_pattern = re.compile(r'([\u4e00-\u9fa5]{2,4})市')
        match = city_pattern.search(text)
        if match:
            return match.group(1)
        return None

    def _extract_airplane_route(self, text: str) -> tuple[Optional[str], Optional[str]]:
        """Extract airplane route (origin, destination)."""
        patterns = self._patterns.get("airplane_route", [])

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                try:
                    origin = match.group(1).strip()
                    destination = match.group(2).strip()
                    return origin, destination
                except IndexError:
                    continue

        return None, None

    def _extract_train_route(self, text: str) -> tuple[Optional[str], Optional[str]]:
        """Extract train route (origin, destination)."""
        patterns = self._patterns.get("train_route", [])

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                try:
                    origin = match.group(1).strip()
                    destination = match.group(2).strip()
                    # Remove "站" suffix if present
                    origin = origin.replace("站", "")
                    destination = destination.replace("站", "")
                    return origin, destination
                except IndexError:
                    continue

        return None, None

    def _extract_taxi_route(self, text: str) -> tuple[Optional[str], Optional[str]]:
        """Extract taxi route (origin, destination)."""
        patterns = self._patterns.get("taxi_route", [])

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                try:
                    origin = match.group(1).strip()
                    destination = match.group(2).strip()
                    # Clean up common suffixes
                    origin = re.sub(r'[站点广场等]+$', '', origin)
                    destination = re.sub(r'[站点广场等]+$', '', destination)
                    return origin, destination
                except IndexError:
                    continue

        return None, None

    def _extract_airport_transfer_route(self, text: str) -> tuple[Optional[str], Optional[str]]:
        """Extract airport transfer route (origin, destination) from trip receipt."""
        patterns = self._patterns.get("airport_transfer_route", [])

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                try:
                    origin = match.group(1).strip()
                    destination = match.group(2).strip()
                    # Clean up common suffixes
                    origin = re.sub(r'[站点广场等]+$', '', origin)
                    destination = re.sub(r'[站点广场等]+$', '', destination)
                    return origin, destination
                except IndexError:
                    continue

        return None, None

    def _extract_hotel_info(self, text: str) -> tuple[Optional[str], Optional[str]]:
        """Extract hotel information (city, hotel name)."""
        patterns = self._patterns.get("hotel_info", [])

        city = self._extract_city(text)

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                try:
                    hotel_name = match.group(1).strip()
                    # Clean up common suffixes
                    hotel_name = re.sub(r'[酒店宾馆有限公司]+$', '', hotel_name)
                    return city, hotel_name
                except IndexError:
                    continue

        return city, None

    def _extract_stay_days(self, text: str) -> Optional[int]:
        """Extract number of stay days from text."""
        patterns = self._patterns.get("stay_days", [])

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                try:
                    days = int(match.group(1))
                    if 0 < days < 365:
                        return days
                except (ValueError, IndexError):
                    continue

        return None
