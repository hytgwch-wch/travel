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
    BILL = "结账单"  # Hotel bill/statement
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

    # Transport trip date range (for taxi, airport transfer, etc.)
    trip_start_date: Optional[date] = None  # Trip start date
    trip_end_date: Optional[date] = None    # Trip end date

    # Hotel specific
    city: Optional[str] = None
    hotel_name: Optional[str] = None
    stay_days: Optional[int] = None
    check_in_date: Optional[date] = None
    check_out_date: Optional[date] = None

    # Statement/Bill specific
    is_statement: bool = False  # True if this is a hotel bill/statement (结账单)

    # Taxi/Trip specific
    is_trip_receipt: bool = False  # True if this is a trip receipt (行程单) for taxi/rides

    # Refund info
    is_refund: bool = False

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
            info.is_refund = self._check_is_refund(text)
            # Try to extract actual flight date from remarks
            # This is needed because the invoice date might be the billing date
            flight_date = self._extract_trip_date_from_invoice(text)
            if flight_date:
                info.date = flight_date
                logger.info(f"Using flight date {flight_date} instead of billing date")

        elif invoice_type == InvoiceType.AIRPORT_TRANSFER:
            info.origin, info.destination = self._extract_airport_transfer_route(text)
            info.transport_mode = "接送机"
            info.is_refund = self._check_is_refund(text)
            # For trip receipts, extract trip date range
            if "行程单" in text or "用车行程单" in text:
                info.is_trip_receipt = True
                start_date, end_date = self._extract_trip_date_range(text)
                if start_date:
                    info.trip_start_date = start_date
                    info.trip_end_date = end_date if end_date else start_date
                    # Use start date as the primary date
                    info.date = start_date
            elif "电子发票" in text or "发票" in text:
                info.is_trip_receipt = False
                # Invoice dates will be matched with trip receipts in scheduler

        elif invoice_type == InvoiceType.TRAIN:
            info.origin, info.destination = self._extract_train_route(text)
            info.transport_mode = "火车"
            info.is_refund = self._check_is_refund(text)

        elif invoice_type == InvoiceType.TAXI:
            info.origin, info.destination = self._extract_taxi_route(text)
            info.transport_mode = "打车/网约车"
            # For DiDi, distinguish between trip receipts (行程单) and invoices (发票)
            # Extract trip date range (start_date, end_date)
            if "行程单" in text or "行程表" in text:
                # This is a trip receipt - extract trip period dates
                info.is_trip_receipt = True
                start_date, end_date = self._extract_trip_date_range(text)
                if start_date:
                    info.trip_start_date = start_date
                    info.trip_end_date = end_date if end_date else start_date
                    # Use start date as the primary date
                    info.date = start_date
            elif "电子发票" in text or "发票" in text:
                # This is an invoice - try to extract trip date (出行日期)
                info.is_trip_receipt = False
                # For invoices, we don't set trip_start_date/end_date from the invoice itself
                # These will be set by the scheduler when matching with trip receipts
                trip_date = self._extract_trip_date_from_invoice(text)
                if trip_date:
                    info.date = trip_date

        elif invoice_type == InvoiceType.HOTEL:
            info.city, info.hotel_name = self._extract_hotel_info(text)
            info.stay_days = self._extract_stay_days(text)
            # Extract hotel stay dates
            check_in, check_out = self._extract_hotel_stay_dates(text)
            info.check_in_date = check_in
            info.check_out_date = check_out
            # Use check-in date as the invoice date if available
            if check_in:
                info.date = check_in

        elif invoice_type == InvoiceType.BILL:
            # Bill/statement - extract hotel stay dates and amount
            info.is_statement = True
            info.city, info.hotel_name = self._extract_hotel_info(text)
            # Extract hotel stay dates (bills usually have this)
            check_in, check_out = self._extract_hotel_stay_dates(text)
            info.check_in_date = check_in
            info.check_out_date = check_out
            # Use check-in date as the bill date if available
            if check_in:
                info.date = check_in
            # Extract amount from bill
            # Bills often show total amount, tax, etc.
            info.amount = self._extract_bill_amount(text)

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

        # Check for bill/statement first (结账单)
        # Check filename and content for bill keywords
        bill_keywords = ["结账单", "账单", "消费明细", "账单明细"]
        if any(kw in text for kw in bill_keywords):
            return InvoiceType.BILL

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

        # Try to extract Chinese amount format (壹贰叁肆伍陆柒捌玖拾佰仟万亿元整角分)
        chinese_num_pattern = r'([零壹贰叁肆伍陆柒捌玖拾佰仟万]+)元'
        chinese_match = re.search(chinese_num_pattern, text)
        if chinese_match:
            # For now, just return 0.0 for Chinese amounts as conversion is complex
            # In production, the filename-based amount would be used instead
            logger.debug("Found Chinese amount format, returning 0.0 (conversion not implemented)")
            return Decimal('0.0')

        return None

    def _extract_traveler(self, text: str) -> Optional[str]:
        """Extract traveler name from text."""
        patterns = self._patterns.get("traveler", [])

        # Invalid traveler names that are placeholders, not real names
        invalid_names = {
            "工号", "员工号", "Employee", "ID", "姓名", "乘车人",
            "乘机人", "旅客", "出行人", "购票人", "预订人",
            "driver", "passenger", "employee", "工号员"
        }

        for pattern in patterns:
            match = pattern.search(text)
            if match:
                try:
                    name = match.group(1).strip()
                    # Skip if it's an invalid placeholder name
                    if name in invalid_names:
                        continue
                    # Skip if it's too short or too long to be a real name
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
        """
        Extract train route (origin, destination).

        12306 ticket format analysis:
        - Top area English station (before train number): DEPARTURE station (most reliable)
        - Top area Chinese stations (before train number): CORRECT order (origin -> destination)
        - Bottom area Chinese stations: REVERSE order (destination -> origin)

        Strategy:
        1. Extract English station from top area as origin (most reliable)
        2. If no English station, extract Chinese stations from top area
        3. Otherwise, extract from all text and swap (reverse order)
        """
        patterns = self._patterns.get("train_route", [])
        chinese_pattern = r'([\u4e00-\u9fa5]{2,5}东站|[\u4e00-\u9fa5]{2,5}南站|[\u4e00-\u9fa5]{2,5}西站|[\u4e00-\u9fa5]{2,5}北站|[\u4e00-\u9fa5]{2,4}站)'

        # Station name mapping (English to Chinese)
        station_map = {
            'Xiamenbei': '厦门北', 'Xiamen': '厦门',
            'Hangzhouxi': '杭州西', 'Hangzhou': '杭州',
            'Hangzhoudong': '杭州东',
            'Shanghaihongqiao': '上海虹桥', 'Shanghai': '上海',
            'Wuxi': '无锡',
            'Danyang': '丹阳',
            'Nanjingnan': '南京南', 'Nanjing': '南京',
            'Huzhou': '湖州',
            'Lishui': '溧水',
            'Nanping': '南平', 'Nanpingshi': '南平市',
        }

        lines = text.split('\n')
        top_area = '\n'.join(lines[:25])

        # Find train number position
        train_match = re.search(r'[A-Z]{1,2}\d{3,4}', top_area)

        # Strategy 1: Extract English station from top area as origin (most reliable)
        # English station appears before train number, pattern: Capital + lowercase letters
        if train_match:
            before_train = top_area[:train_match.start()]
            # Match English station names (3-20 letters)
            en_station_match = re.search(r'\b([A-Z][a-z]{3,20})\b', before_train)
            if en_station_match:
                en_origin = en_station_match.group(1)
                if en_origin in station_map:
                    cn_origin = station_map[en_origin]
                    # Find destination from Chinese stations
                    all_chinese_stations = re.findall(chinese_pattern, text)
                    # Filter out origin, find destination
                    for station in all_chinese_stations:
                        cn_station = station.replace("站", "")
                        if cn_station != cn_origin and cn_station in station_map.values():
                            destination = cn_station
                            logger.debug(f"Route from English top station: {cn_origin} -> {destination}")
                            return cn_origin, destination

        # Strategy 2: Extract Chinese stations from top area (before train number)
        if train_match:
            before_train = top_area[:train_match.start()]
            top_stations = re.findall(chinese_pattern, before_train)
            if len(top_stations) >= 2:
                # Top area stations are in correct order: origin, destination
                origin = top_stations[0].replace("站", "")
                destination = top_stations[1].replace("站", "")
                logger.debug(f"Route from top Chinese stations: {origin} -> {destination}")
                return origin, destination

        # Strategy 3: Extract from all text (bottom area stations)
        # These are in REVERSE order: destination first, origin second
        chinese_stations = re.findall(chinese_pattern, text)
        if len(chinese_stations) >= 2:
            # Swap to get correct order: origin (second), destination (first)
            origin = chinese_stations[1].replace("站", "")
            destination = chinese_stations[0].replace("站", "")
            logger.debug(f"Route from bottom area (swapped): {origin} -> {destination}")
            return origin, destination

        # Fallback to pattern matching if Chinese extraction fails
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                try:
                    first = match.group(1).strip()
                    second = match.group(2).strip()

                    # For non-Chinese patterns, check if it's English
                    is_english = (
                        first and
                        first[0].isupper() and first[1].islower() and
                        second and
                        second[0].isupper() and second[1].islower()
                    )

                    # For both Chinese and English from patterns: don't swap
                    # The order in the ticket text is generally origin -> destination
                    origin, destination = first, second

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

    def _check_is_refund(self, text: str) -> bool:
        """Check if invoice is a refund fee."""
        patterns = self._patterns.get("is_refund", [])
        for pattern in patterns:
            if pattern.search(text):
                return True
        return False

    def _extract_hotel_stay_dates(self, text: str) -> tuple[Optional[date], Optional[date]]:
        """Extract hotel stay dates (check-in and check-out)."""
        # Define patterns directly with DOTALL flag for multi-line matching
        pattern_definitions = [
            # Format: 入住日期:2026年03月11日  退房日期:2026年03月12日
            r'入住日期[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日.*?退房日期[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日',
            # Format: 入住日期 2026-02-24 离店日期/离开日期 2026-02-25 (结账单格式，支持换行)
            r'入住日期.*?(\d{4})-(\d{1,2})-(\d{1,2}).*?离[开店]日期.*?(\d{4})-(\d{1,2})-(\d{1,2})',
            # Format: 2026.03.11-2026.03.12
            r'(\d{4})\.(\d{1,2})\.(\d{1,2})\s*[-\-~到至]\s*(\d{4})\.(\d{1,2})\.(\d{1,2})',
            # Format: 2026-03-11至2026-03-12
            r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s*[-\-~到至]\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})',
        ]

        for pattern_str in pattern_definitions:
            pattern = re.compile(pattern_str, re.DOTALL)
            match = pattern.search(text)
            if match:
                try:
                    groups = match.groups()
                    if len(groups) >= 6:
                        # Format: YYYY-MM-DD to YYYY-MM-DD
                        year1, month1, day1 = groups[0], groups[1], groups[2]
                        year2, month2, day2 = groups[3], groups[4], groups[5]
                        check_in = datetime.strptime(f"{year1}-{month1.zfill(2)}-{day1.zfill(2)}", "%Y-%m-%d").date()
                        check_out = datetime.strptime(f"{year2}-{month2.zfill(2)}-{day2.zfill(2)}", "%Y-%m-%d").date()
                        logger.info(f"Extracted stay dates: {check_in} to {check_out}")
                        return check_in, check_out
                except (ValueError, IndexError):
                    continue

        return None, None

    def _extract_bill_amount(self, text: str) -> Optional[Decimal]:
        """
        Extract total amount from hotel bill/statement.

        Bills may have different format than invoices:
        - 总金额, 合计, 消费总额, etc.
        - May include tax breakdown
        """
        # Try bill-specific patterns first (with DOTALL for multi-line)
        # Patterns use .*? to match across newlines
        bill_amount_patterns = [
            r'总金额.*?(\d+\.\d{2})',
            r'合计.*?(\d+\.\d{2})',
            r'消费合计.*?(\d+\.\d{2})',
            r'付款合计.*?(\d+\.\d{2})',
            r'消费总额.*?(\d+\.\d{2})',
            r'应收金额.*?(\d+\.\d{2})',
            r'应付金额.*?(\d+\.\d{2})',
            r'总计.*?(\d+\.\d{2})',
        ]

        for pattern_str in bill_amount_patterns:
            match = re.search(pattern_str, text, re.DOTALL)
            if match:
                try:
                    amount_str = match.group(1).replace(",", "")
                    return Decimal(amount_str)
                except (ValueError, IndexError):
                    continue

        # Fall back to standard amount extraction
        return self._extract_amount(text)

    def _extract_didi_trip_date(self, text: str) -> Optional[date]:
        """
        Extract trip date from DiDi trip receipt.

        DiDi trip receipts (行程单) have format like:
        · 行程起止日期：2026-01-28 至 2026-02-27

        Returns the earliest trip date.
        """
        # Pattern for DiDi trip period: 行程起止日期：YYYY-MM-DD 至 YYYY-MM-DD
        pattern = r'行程起止日期[：:]\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*至.*?(\d{4})-(\d{1,2})-(\d{1,2})'
        match = re.search(pattern, text)
        if match:
            try:
                year, month, day = match.group(1), match.group(2), match.group(3)
                trip_date = datetime.strptime(f"{year}-{month.zfill(2)}-{day.zfill(2)}", "%Y-%m-%d").date()
                logger.info(f"Extracted DiDi trip date: {trip_date}")
                return trip_date
            except ValueError:
                pass

        # Also try individual trip dates in the table
        # Format: 01-28 07:16 周三
        pattern = r'(\d{2})-(\d{2})\s+\d{2}:\d{2}'
        match = re.search(pattern, text)
        if match:
            try:
                month, day = match.group(1), match.group(2)
                # Need to infer year - use current year or previous year if dates are in future
                current_date = datetime.now().date()
                trip_date = datetime.strptime(f"{current_date.year}-{month}-{day}", "%Y-%m-%d").date()
                # If trip date is in the future, it might be from last year
                if trip_date > current_date:
                    trip_date = datetime.strptime(f"{current_date.year - 1}-{month}-{day}", "%Y-%m-%d").date()
                logger.info(f"Extracted DiDi trip date from table: {trip_date}")
                return trip_date
            except ValueError:
                pass

        return None

    def _extract_trip_date_range(self, text: str) -> tuple[Optional[date], Optional[date]]:
        """
        Extract trip date range (start_date, end_date) from trip receipt.

        For taxi and airport transfer trip receipts.
        Returns (start_date, end_date) tuple.
        """
        # Pattern 1: 行程起止日期：YYYY-MM-DD 至 YYYY-MM-DD
        pattern = r'行程起止日期[：:]\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*[-至到]\s*(\d{4})-(\d{1,2})-(\d{1,2})'
        match = re.search(pattern, text)
        if match:
            try:
                start_year, start_month, start_day = match.group(1), match.group(2), match.group(3)
                end_year, end_month, end_day = match.group(4), match.group(5), match.group(6)
                start_date = datetime.strptime(f"{start_year}-{start_month.zfill(2)}-{start_day.zfill(2)}", "%Y-%m-%d").date()
                end_date = datetime.strptime(f"{end_year}-{end_month.zfill(2)}-{end_day.zfill(2)}", "%Y-%m-%d").date()
                logger.info(f"Extracted trip date range: {start_date} to {end_date}")
                return start_date, end_date
            except ValueError:
                pass

        # Pattern 2: 行程日期：YYYY-MM-DD至YYYY-MM-DD or YYYY年MM月DD日至YYYY年MM月DD日
        pattern = r'行程日期[：:]\s*(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})\s*[-至到]\s*(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})'
        match = re.search(pattern, text)
        if match:
            try:
                start_year, start_month, start_day = match.group(1), match.group(2), match.group(3)
                end_year, end_month, end_day = match.group(4), match.group(5), match.group(6)
                start_date = datetime.strptime(f"{start_year}-{start_month.zfill(2)}-{start_day.zfill(2)}", "%Y-%m-%d").date()
                end_date = datetime.strptime(f"{end_year}-{end_month.zfill(2)}-{end_day.zfill(2)}", "%Y-%m-%d").date()
                logger.info(f"Extracted trip date range: {start_date} to {end_date}")
                return start_date, end_date
            except ValueError:
                pass

        # Pattern 3: 单个行程日期 YYYY-MM-DD
        pattern = r'(?:行程日期|用车时间)[：:]\s*(\d{4})-(\d{1,2})-(\d{1,2})(?!\s*[-至到])'
        match = re.search(pattern, text)
        if match:
            try:
                year, month, day = match.group(1), match.group(2), match.group(3)
                trip_date = datetime.strptime(f"{year}-{month.zfill(2)}-{day.zfill(2)}", "%Y-%m-%d").date()
                logger.info(f"Extracted single trip date: {trip_date}")
                return trip_date, trip_date
            except ValueError:
                pass

        return None, None

    def _extract_trip_date_from_invoice(self, text: str) -> Optional[date]:
        """
        Extract trip date (出行日期) from invoice.

        For flight invoices, extract the actual flight date from the remarks.
        For taxi/DiDi invoices, extract the trip date field.
        """
        # Pattern for flight date in remarks: 备注中包含航班日期
        # Format: 2026-03-23 北京-上海 CA1234
        # Pattern: YYYY/MM/DD or YYYY-MM-DD followed by city names
        flight_pattern = r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})\s+[\u4e00-\u9fa5]+[-\-→][\u4e00-\u9fa5]+\s+[A-Z]{2}\d+'
        match = re.search(flight_pattern, text)
        if match:
            try:
                year, month, day = match.group(1), match.group(2), match.group(3)
                trip_date = datetime.strptime(f"{year}-{month.zfill(2)}-{day.zfill(2)}", "%Y-%m-%d").date()
                logger.info(f"Extracted flight date from remarks: {trip_date}")
                return trip_date
            except ValueError:
                pass

        # Pattern for 携程订单 format: 携程订单:xxx,2026/2/10 ...
        ctrip_pattern = r'携程订单[：:,]\s*\d+[,，]\s*(\d{4})[//-](\d{1,2})[/\-](\d{1,2})'
        match = re.search(ctrip_pattern, text)
        if match:
            try:
                year, month, day = match.group(1), match.group(2), match.group(3)
                trip_date = datetime.strptime(f"{year}-{month.zfill(2)}-{day.zfill(2)}", "%Y-%m-%d").date()
                logger.info(f"Extracted flight date from Ctrip order: {trip_date}")
                return trip_date
            except ValueError:
                pass

        # Pattern for taxi 出行日期：YYYY年MM月DD日
        taxi_pattern = r'出行日期[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日'
        match = re.search(taxi_pattern, text)
        if match:
            try:
                year, month, day = match.group(1), match.group(2), match.group(3)
                trip_date = datetime.strptime(f"{year}-{month.zfill(2)}-{day.zfill(2)}", "%Y-%m-%d").date()
                logger.info(f"Extracted trip date from taxi invoice: {trip_date}")
                return trip_date
            except ValueError:
                pass

        return None
