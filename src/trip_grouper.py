"""
Trip grouper module.

Groups invoices into complete business trips based on:
- Traveler
- Destination city
- Date sequence (departure from Hangzhou -> activities -> return to Hangzhou)
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
from collections import defaultdict
from datetime import timedelta

from loguru import logger


@dataclass
class Invoice:
    """Invoice information extracted from filename."""
    filename: str
    filepath: Path
    date: date
    invoice_type: str  # 机票, 火车, 接送机, etc.
    origin: Optional[str] = None
    destination: Optional[str] = None
    amount: float = 0.0
    traveler: str = ""
    document_type: str = ""  # 行程单, 发票, or empty

    def __str__(self) -> str:
        return f"{self.date} {self.invoice_type} {self.origin or ''}->{self.destination or ''} {self.traveler}"

    @classmethod
    def from_filename(cls, filepath: Path) -> 'Invoice':
        """Extract invoice info from filename.

        Filename formats:
        - Flight/Train: {date}_{type}_{origin}_{destination}_{amount}_{traveler}_{doc_type}.pdf
          Example: 2026-02-10_机票_杭州_青岛_1065.00_王春晖.pdf
        - Airport Transfer (detailed): {date_range}_{type}_{route}_{amount}_{traveler}_{doc_type}.pdf
          Example: 2026-03-01至2026-03-01_接送机_首都国际机场_T3_北京华融大厦_133.00_王春晖_行程单.pdf
        - Taxi (simple): {date_range}_{type}_{amount}_{traveler}_{doc_type}.pdf
          Example: 2026-01-28至2026-01-28_打车_17.40_王春晖_发票.pdf
        - Accommodation: {date_range}_{type}_{amount}_{traveler}.pdf
          Example: 2026-02-24_2026-02-25_住宿_342.02_王春晖.pdf
        """
        name = filepath.stem

        # Parse filename
        parts = name.split('_')

        if len(parts) < 4:
            logger.warning(f"Cannot parse filename: {name}")
            return None

        try:
            # Date - handle both single date and date range formats
            # Single date: 2026-02-10
            # Date range: 2026-01-28至2026-01-28 or 2026-01-28至2026-02-27
            # For accommodation, it might be: 2026-02-24_2026-02-25 (start_end format)
            date_str = parts[0]
            if '至' in date_str:
                # Date range format - extract start date
                start_date_str = date_str.split('至')[0]
                invoice_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            elif len(parts) > 1 and re.match(r'\d{4}-\d{2}-\d{2}', parts[1]):
                # Accommodation format: 2026-02-24_2026-02-25
                invoice_date = datetime.strptime(parts[0], "%Y-%m-%d").date()
            else:
                # Single date format
                invoice_date = datetime.strptime(date_str, "%Y-%m-%d").date()

            # Type - determine by checking each part for known invoice types
            invoice_type = None
            type_idx = 1
            for i, part in enumerate(parts[1:], start=1):
                if part in ["机票", "火车", "接送机", "打车", "住宿", "餐饮", "结账单"]:
                    invoice_type = part
                    type_idx = i
                    break

            if not invoice_type:
                # If no type found, use second part as type (fallback)
                if len(parts) > 1:
                    invoice_type = parts[1]
                else:
                    logger.warning(f"Cannot determine invoice type: {name}")
                    return None

            # Origin and destination (for flights/trains/airport transfers)
            origin = None
            destination = None
            amount = 0.0
            traveler = ""
            doc_type = ""

            # Parse based on invoice type
            if invoice_type in ["机票", "火车"]:
                # Format: {date}_{type}_{origin}_{destination}_{amount}_{traveler}_{doc_type}
                # OR: {date}_{type}_{origin}_{amount}_{traveler} (when destination is skipped)
                if len(parts) >= 5:
                    origin = parts[2]
                    # Check if parts[3] is a destination or an amount
                    if re.match(r'^\d+\.\d{2}$', parts[3]):
                        # parts[3] is amount, destination is missing or skipped
                        amount = float(parts[3])
                        if len(parts) > 4:
                            traveler = parts[4]
                        if len(parts) > 5 and parts[5] in ["行程单", "发票"]:
                            doc_type = parts[5]
                    else:
                        # parts[3] is destination
                        destination = parts[3]
                        # Find amount
                        for i in range(3, len(parts)):
                            amount_match = re.match(r'(\d+\.\d{2})', parts[i])
                            if amount_match:
                                amount = float(amount_match.group(1))
                                if i + 1 < len(parts):
                                    traveler = parts[i + 1]
                                if i + 2 < len(parts) and parts[i + 2] in ["行程单", "发票"]:
                                    doc_type = parts[i + 2]
                                break

            elif invoice_type == "接送机":
                # Format: {date}_{type}_{route_parts}_{amount}_{traveler}_{doc_type}
                # OR: {date}_{type}_{amount}_{traveler}_{doc_type} (simple format)
                # Check if there's route info (look for amount after non-numeric parts)
                amount_idx = None
                for i in range(2, len(parts)):
                    if re.match(r'^\d+\.\d{2}$', parts[i]):
                        amount_idx = i
                        break

                if amount_idx and amount_idx > 2:
                    # Has route info between type and amount
                    route_parts = parts[2:amount_idx]
                    origin = "_".join(route_parts)
                    amount = float(parts[amount_idx])
                    if amount_idx + 1 < len(parts):
                        traveler = parts[amount_idx + 1]
                    if amount_idx + 2 < len(parts) and parts[amount_idx + 2] in ["行程单", "发票"]:
                        doc_type = parts[amount_idx + 2]
                elif amount_idx:
                    # Simple format: type followed immediately by amount
                    amount = float(parts[amount_idx])
                    if amount_idx + 1 < len(parts):
                        traveler = parts[amount_idx + 1]
                    if amount_idx + 2 < len(parts) and parts[amount_idx + 2] in ["行程单", "发票"]:
                        doc_type = parts[amount_idx + 2]

            elif invoice_type in ["打车", "餐饮"]:
                # Format: {date_range}_{type}_{amount}_{traveler}_{doc_type}
                # Find amount
                for i in range(2, len(parts)):
                    amount_match = re.match(r'(\d+\.\d{2})', parts[i])
                    if amount_match:
                        amount = float(amount_match.group(1))
                        if i + 1 < len(parts):
                            traveler = parts[i + 1]
                        if i + 2 < len(parts) and parts[i + 2] in ["行程单", "发票"]:
                            doc_type = parts[i + 2]
                        break

            elif invoice_type in ["住宿", "结账单"]:
                # Format: {date_range}_{type}_{amount}_{traveler}
                # OR: {date_range}_{type}_{amount}_{traveler} (no doc_type)
                # Find amount
                for i in range(2, len(parts)):
                    amount_match = re.match(r'(\d+\.\d{2})', parts[i])
                    if amount_match:
                        amount = float(amount_match.group(1))
                        if i + 1 < len(parts):
                            traveler = parts[i + 1]
                        # No doc_type for accommodation
                        break
                # Normalize type
                if invoice_type == "结账单":
                    invoice_type = "住宿"

            return cls(
                filename=filepath.name,
                filepath=filepath,
                date=invoice_date,
                invoice_type=invoice_type,
                origin=origin,
                destination=destination,
                amount=amount,
                traveler=traveler,
                document_type=doc_type
            )

        except Exception as e:
            logger.error(f"Error parsing filename {name}: {e}")
            return None


@dataclass
class Trip:
    """A complete business trip."""
    trip_id: str
    traveler: str
    start_date: date
    end_date: date
    destination: str
    invoices: List[Invoice] = field(default_factory=list)
    departure_transfer: Optional[Invoice] = None
    return_transfer: Optional[Invoice] = None
    cities: List[str] = field(default_factory=list)  # All cities visited

    def __str__(self) -> str:
        return f"Trip: {self.traveler} -> {self.destination} ({self.start_date} to {self.end_date}, {len(self.invoices)} invoices)"


@dataclass
class TripTransfer:
    """Airport transfer information."""
    invoices: List[Invoice]  # All related invoices for this transfer
    trip_date: date  # The associated flight/train date
    direction: str  # "出发" (departure) or "返回" (return)


class TripGrouper:
    """
    Group invoices into complete business trips.

    A complete trip:
    - Starts in Hangzhou (departure)
    - Goes to destination city
    - Returns to Hangzhou
    """

    HOME_CITY = "杭州"

    # Province mapping for geographic proximity判断
    PROVINCE_MAP = {
        # Zhejiang Province
        "杭州": "浙江", "杭州南": "浙江", "杭州东": "浙江", "杭州西": "浙江", "临平": "浙江",
        "宁波": "浙江", "温州": "浙江", "嘉兴": "浙江", "湖州": "浙江",
        "绍兴": "浙江", "金华": "浙江", "衢州": "浙江", "舟山": "浙江",
        "台州": "浙江", "丽水": "浙江",
        # Shanghai
        "上海": "上海", "上海虹桥": "上海",
        # Jiangsu Province
        "南京": "江苏", "南京南": "江苏", "苏州": "江苏", "无锡": "江苏", "常州": "江苏",
        "镇江": "江苏", "南通": "江苏", "泰州": "江苏", "扬州": "江苏",
        "丹阳": "江苏", "溧水": "江苏", "徐州": "江苏",
        # Beijing
        "北京": "北京", "首都国际机场": "北京",
        # Liaoning Province
        "大连": "辽宁", "沈阳": "辽宁", "鞍山": "辽宁",
        # Heilongjiang Province
        "哈尔滨": "黑龙江", "齐齐哈尔": "黑龙江",
        # Jilin Province
        "长春": "吉林", "吉林": "吉林", "延吉": "吉林",
        # Shandong Province
        "青岛": "山东", "济南": "山东", "烟台": "山东",
        # Chongqing
        "重庆": "重庆",
        # Others (add as needed)
        "太平湖": "安徽", "太湖南": "安徽", "南平市": "福建", "厦门北": "福建",
    }

    def __init__(self, invoices_dir: str = "invoices"):
        """Initialize trip grouper."""
        self.invoices_dir = Path(invoices_dir)

    def group_by_trip(self) -> List[Trip]:
        """
        Group all invoices into complete business trips.

        Returns:
            List of Trip objects
        """
        # Collect all invoices
        invoices = self._collect_invoices()

        if not invoices:
            logger.warning("No invoices found")
            return []

        # Group by traveler (skip invoices without traveler)
        by_traveler = defaultdict(list)
        for inv in invoices:
            if inv.traveler:  # Only group invoices with valid traveler
                by_traveler[inv.traveler].append(inv)

        # Find trips for each traveler
        all_trips = []
        trip_counter = 1

        for traveler, traveler_invoices in by_traveler.items():
            # Sort by date, and prioritize departure from home on same date
            # This ensures Hangzhou->XXX is processed before XXX->YYY on same day
            def sort_key(inv):
                # Primary sort: date
                # Secondary sort: departure from home first (0), then others (1)
                priority = 0 if self._is_departure_from_home(inv) else 1
                return (inv.date, priority)

            traveler_invoices.sort(key=sort_key)

            # Find trip segments
            trips = self._find_trips_for_traveler(traveler, traveler_invoices)

            for trip in trips:
                trip.trip_id = f"T{trip_counter:03d}_{traveler}_{trip.start_date.strftime('%Y%m%d')}"
                trip_counter += 1
                all_trips.append(trip)

        return all_trips

    def _collect_invoices(self) -> List[Invoice]:
        """Collect all invoice information from filenames."""
        invoices = []

        for pdf_file in self.invoices_dir.rglob("*.pdf"):
            inv = Invoice.from_filename(pdf_file)
            # Only add valid invoices with a date
            if inv and inv.date:
                invoices.append(inv)

        logger.info(f"Collected {len(invoices)} invoices")
        return invoices

    def _normalize_city(self, city: str) -> Optional[str]:
        """
        Normalize city name for matching.

        Removes station suffixes and maps to standard city names.

        Args:
            city: Raw city name from invoice

        Returns:
            Normalized city name or None
        """
        if not city:
            return None

        # Handle complex route strings (e.g., "首都国际机场_T3_北京华融大厦")
        # Split by common separators and check each part
        if '_' in city:
            parts = city.split('_')
            for part in parts:
                normalized = self._normalize_city(part)
                if normalized and normalized != self.HOME_CITY:
                    return normalized

        # Remove train station suffixes (东, 南, 西, 北)
        # But be careful not to remove actual city names
        # Only remove if the base city is known
        if city.endswith("东") or city.endswith("南") or city.endswith("西") or city.endswith("北"):
            base_city = city[:-1]
            # Check if base is in our province map (known city)
            if base_city in self.PROVINCE_MAP:
                return base_city

        # Direct aliases for special cases
        aliases = {
            "上海虹桥": "上海",
            "临平": "杭州",  # 临平区 is part of Hangzhou
            "首都国际机场": "北京",
            "萧山国际机场": "杭州",
            "浦东国际机场": "上海",
        }

        # Check direct aliases
        if city in aliases:
            return aliases[city]

        # Check if any part of the city name is in our province map
        # This handles cases like "北京华融大厦" -> "北京"
        for known_city in self.PROVINCE_MAP.keys():
            if known_city in city or city in known_city:
                return known_city

        return city

    def _cities_nearby(self, city1: Optional[str], city2: Optional[str]) -> bool:
        """
        Check if two cities are nearby (same province for geographic proximity).

        Args:
            city1: First city name
            city2: Second city name

        Returns:
            True if cities are in the same province
        """
        if not city1 or not city2:
            return False

        # Direct match
        if city1 == city2:
            return True

        # Check if same province
        prov1 = self.PROVINCE_MAP.get(city1)
        prov2 = self.PROVINCE_MAP.get(city2)

        return prov1 and prov2 and prov1 == prov2

    def _build_trip_chains(self, journey_invoices: List[Invoice]) -> Tuple[List[List[Invoice]], List[List[Invoice]]]:
        """
        Build chains of journey segments for trips.

        A complete trip:
        - Starts from Hangzhou (journey departure)
        - May include multiple segments (multi-city trip)
        - Ends when returning to Hangzhou OR no more connections

        Args:
            journey_invoices: List of journey invoices (机票/火车 with routes)

        Returns:
            Tuple of (complete_chains, incomplete_chains)
            - complete_chains: Chains starting from Hangzhou
            - incomplete_chains: Other journeys (orphans)
        """
        complete_chains = []
        incomplete_chains = []
        used_indices = set()

        # Sort by date
        sorted_invoices = sorted(journey_invoices, key=lambda x: x.date)

        for i, inv in enumerate(sorted_invoices):
            if i in used_indices:
                continue

            origin_city = self._normalize_city(inv.origin)
            dest_city = self._normalize_city(inv.destination)

            if not origin_city or not dest_city:
                continue

            # Check if this departs from Hangzhou (complete trip start)
            if origin_city == self.HOME_CITY:
                # Start a new chain
                chain = [inv]
                current_dest = dest_city
                used_indices.add(i)

                # Find connecting journeys within this trip
                # Stop when: no more connections OR hit another Hangzhou departure
                for j in range(i + 1, len(sorted_invoices)):
                    if j in used_indices:
                        continue

                    next_inv = sorted_invoices[j]
                    next_origin = self._normalize_city(next_inv.origin)
                    next_dest = self._normalize_city(next_inv.destination)

                    if not next_origin or not next_dest:
                        continue

                    # Check if next journey starts from current destination (or nearby)
                    # AND date is after or same day
                    #
                    # IMPORTANT: When current_dest is home city, use exact match only
                    # to avoid connecting unrelated trips within the same province
                    if current_dest == self.HOME_CITY:
                        # Exact match required when at home city
                        origin_matches = (next_origin == current_dest)
                    else:
                        # Allow nearby cities when not at home
                        origin_matches = (next_origin == current_dest or
                                        self._cities_nearby(next_origin, current_dest))

                    if origin_matches and next_inv.date >= sorted_invoices[i].date:
                        # Check if next journey starts from Hangzhou (new trip)
                        if next_origin == self.HOME_CITY and j > i:
                            # This is a new trip, don't include it
                            break

                        chain.append(next_inv)
                        used_indices.add(j)
                        current_dest = next_dest

                        # If returned to Hangzhou, stop the chain
                        # Each departure from home is a separate trip
                        if current_dest == self.HOME_CITY:
                            break

                    # Stop if next journey starts from Hangzhou (new trip)
                    if next_origin == self.HOME_CITY and j > i:
                        break

                complete_chains.append(chain)

        # Handle remaining unused journeys - try to build connected chains
        # These are journeys that don't start from Hangzhou but may form continuous routes
        remaining_indices = [i for i in range(len(sorted_invoices)) if i not in used_indices]

        # Sort remaining by date
        remaining_indices.sort(key=lambda i: sorted_invoices[i].date)

        for i in remaining_indices:
            if i in used_indices:
                continue

            # Try to build a chain starting from this journey
            chain = [sorted_invoices[i]]
            current_dest = self._normalize_city(sorted_invoices[i].destination)
            used_indices.add(i)

            # Find connecting journeys (same or nearby origin -> current destination)
            connected = True
            while connected:
                connected = False
                for j in remaining_indices:
                    if j in used_indices:
                        continue

                    next_inv = sorted_invoices[j]
                    next_origin = self._normalize_city(next_inv.origin)
                    next_dest = self._normalize_city(next_inv.destination)

                    if not next_origin or not next_dest:
                        continue

                    # Check if next journey starts from current destination (or nearby)
                    # Use same logic as above: exact match when at home, allow nearby otherwise
                    if current_dest == self.HOME_CITY:
                        origin_matches = (next_origin == current_dest)
                    else:
                        origin_matches = (next_origin == current_dest or
                                        self._cities_nearby(next_origin, current_dest))

                    if origin_matches and next_inv.date >= sorted_invoices[i].date:
                        chain.append(next_inv)
                        used_indices.add(j)
                        current_dest = next_dest
                        connected = True
                        break

            if len(chain) > 1:
                # Multi-journey chain found
                incomplete_chains.append(chain)
            else:
                # Single orphan journey
                incomplete_chains.append(chain)

        return complete_chains, incomplete_chains

    def _find_trips_for_traveler(self, traveler: str, invoices: List[Invoice]) -> List[Trip]:
        """
        Find complete trips for a single traveler using journey chain logic.

        Args:
            traveler: Traveler name
            invoices: Sorted list of invoices for this traveler

        Returns:
            List of Trip objects
        """
        # 1. Separate journey invoices from support invoices
        journey_invoices = [inv for inv in invoices
                            if inv.invoice_type in ['机票', '火车']
                            and inv.origin and inv.destination]
        support_invoices = [inv for inv in invoices
                            if inv not in journey_invoices]

        # 2. Build trip chains from journey invoices
        complete_chains, incomplete_chains = self._build_trip_chains(journey_invoices)

        logger.info(f"Built {len(complete_chains)} complete chains, {len(incomplete_chains)} orphan chains")

        # 3. Create Trip objects
        trips = []

        # Process complete chains
        for i, chain in enumerate(complete_chains):
            trip = self._create_trip_from_chain(traveler, chain, support_invoices, complete=True)
            if trip:
                trips.append(trip)

        # Process orphan/incomplete chains
        for i, chain in enumerate(incomplete_chains):
            trip = self._create_trip_from_chain(traveler, chain, support_invoices, complete=False)
            if trip:
                trips.append(trip)

        return trips

    def _match_transfers(self, invoices: List[Invoice]) -> Dict[Tuple[date, str], TripTransfer]:
        """
        Match airport transfer invoices with their associated flight/train dates.

        Also finds all related invoices (same route, different document types) for each transfer.

        Args:
            invoices: List of invoices

        Returns:
            Dict mapping (date, direction) to TripTransfer info
        """
        transfers = {}
        transfer_invoices = [inv for inv in invoices if inv.invoice_type == "接送机"]

        # Group transfer invoices by route to find related documents
        # Route signature: origin + destination + amount
        route_groups = defaultdict(list)
        for inv in transfer_invoices:
            # Create route signature for matching
            route_key = (inv.origin, inv.destination, inv.amount)
            route_groups[route_key].append(inv)

        for transfer_inv in transfer_invoices:
            # Find associated flight/train by closest date
            closest_invoice = None
            min_diff = None

            for inv in invoices:
                if inv.invoice_type in ["机票", "火车"] and inv.origin and inv.destination:
                    diff = abs((inv.date - transfer_inv.date).days)
                    # Match within 3 days to handle transfers a day before/after flights
                    if diff <= 3:
                        if min_diff is None or diff < min_diff:
                            min_diff = diff
                            closest_invoice = inv

            if closest_invoice:
                # Determine direction: transfer before flight = departure, after = return
                if transfer_inv.date <= closest_invoice.date:
                    direction = "出发"
                else:
                    direction = "返回"

                # Find all related invoices for this transfer (same route, different doc types)
                route_key = (transfer_inv.origin, transfer_inv.destination, transfer_inv.amount)
                related_invoices = route_groups.get(route_key, [])

                transfers[(closest_invoice.date, direction)] = TripTransfer(
                    invoices=related_invoices,  # All related invoices
                    trip_date=closest_invoice.date,
                    direction=direction
                )

        return transfers

    def _is_departure_from_home(self, inv: Invoice) -> bool:
        """Check if invoice represents departure from home city."""
        if inv.invoice_type == "接送机":
            # If route contains home city and airport, it's departure
            return inv.origin and self.HOME_CITY in inv.origin

        # Flight/train from home
        return (inv.origin and self.HOME_CITY in inv.origin and
                inv.destination and self.HOME_CITY not in inv.destination)

    def _is_return_to_home(self, inv: Invoice) -> bool:
        """Check if invoice represents return to home city."""
        if inv.invoice_type == "接送机":
            # If destination contains home city, it's return
            return inv.destination and self.HOME_CITY in inv.destination

        # Flight/train to home
        return (inv.destination and self.HOME_CITY in inv.destination and
                inv.origin and self.HOME_CITY not in inv.origin)

    def _extract_city_from_route(self, inv: Invoice) -> str:
        """Extract destination city from route, with normalization."""
        if inv.destination:
            # First normalize the city name
            normalized = self._normalize_city(inv.destination)
            if normalized:
                return normalized
            # Fallback: extract first 2 characters
            city_match = re.match(r'([\u4e00-\u9fa5]{2})', inv.destination)
            if city_match:
                return city_match.group(1)
        return "未知"

    def _create_trip(self, traveler: str, start_date: date, destination: str,
                     invoices: List[Invoice], transfers: Dict[Tuple[date, str], TripTransfer]) -> Optional[Trip]:
        """Create a Trip object with associated transfers."""
        if not invoices:
            return None

        # Ensure we have a valid start_date
        if not start_date:
            # Use the earliest invoice date as start_date
            start_date = min((inv.date for inv in invoices if inv.date), default=None)
            if not start_date:
                logger.warning(f"Cannot create trip for {traveler}: no valid dates")
                return None

        # Calculate end date from latest invoice
        end_date = max(inv.date for inv in invoices if inv.date)

        # Collect all cities visited (excluding home city and airport names)
        cities = []
        cities_set = set()

        # Airport names to exclude from city list
        airport_keywords = ["机场", "萧山", "T1", "T2", "T3", "航站楼"]

        for inv in invoices:
            # Extract origin city
            if inv.origin:
                city = self._extract_city_from_route(inv)
                # Filter out home city, airport names, and unknown
                if (city and city != self.HOME_CITY and
                    city != "未知" and
                    not any(kw in inv.origin for kw in airport_keywords)):
                    if city not in cities_set:
                        cities_set.add(city)
                        cities.append(city)

            # Extract destination city
            if inv.destination:
                city = self._extract_city_from_route(inv)
                # Filter out home city, airport names, and unknown
                if (city and city != self.HOME_CITY and
                    city != "未知" and
                    not any(kw in inv.destination for kw in airport_keywords)):
                    if city not in cities_set:
                        cities_set.add(city)
                        cities.append(city)

        # If no cities collected, use the main destination
        if not cities and destination:
            cities.append(destination)

        # Find associated transfers
        departure_transfer = None
        return_transfer = None

        if start_date and destination:
            # Look for transfers matching this trip
            # Use actual trip duration (start_date to end_date) for matching
            for (date, direction), transfer in transfers.items():
                # Allow transfers from a day before departure through a day after return
                trip_start_buffer = start_date - timedelta(days=1)
                trip_end_buffer = end_date + timedelta(days=1)
                if trip_start_buffer <= date <= trip_end_buffer:
                    if direction == "出发":
                        departure_transfer = transfer  # TripTransfer object
                    elif direction == "返回":
                        return_transfer = transfer  # TripTransfer object

        return Trip(
            trip_id="",  # Will be set by caller
            traveler=traveler,
            start_date=start_date,
            end_date=end_date,
            destination=destination,
            invoices=invoices,
            departure_transfer=departure_transfer,
            return_transfer=return_transfer,
            cities=cities
        )

    def _create_trip_from_chain(self, traveler: str, chain: List[Invoice],
                               support_invoices: List[Invoice], complete: bool = True) -> Optional[Trip]:
        """
        Create Trip from journey chain and match support invoices.

        Args:
            traveler: Traveler name
            chain: List of journey invoices forming a trip chain
            support_invoices: List of support invoices (接送机, 打车, 住宿, etc.)
            complete: Whether this is a complete trip (starts/ends in Hangzhou)

        Returns:
            Trip object or None
        """
        if not chain:
            return None

        # Trip dates
        start_date = chain[0].date
        end_date = chain[-1].date

        # Get all cities visited (including origin of first journey)
        cities = []
        cities_set = set()

        # Add origin city of first journey (important for incomplete trips)
        first_origin = self._normalize_city(chain[0].origin)
        if first_origin and first_origin != self.HOME_CITY:
            cities_set.add(first_origin)
            cities.append(first_origin)

        # Add destination cities
        for inv in chain:
            dest_city = self._normalize_city(inv.destination)
            if dest_city and dest_city != self.HOME_CITY:
                if dest_city not in cities_set:
                    cities_set.add(dest_city)
                    cities.append(dest_city)

        # Trip name based on completeness
        if not cities:
            trip_name = "其他行程"  # Other/incomplete journey
        else:
            trip_name = "-".join(cities)  # e.g., "无锡-丹阳-南京-溧水-湖州"

        # Match support invoices by time range AND geographic relevance
        trip_invoices = list(chain)  # Start with journey invoices

        # Add buffer days for transfers (max 1 day before and after)
        trip_start = start_date - timedelta(days=1)
        trip_end = end_date + timedelta(days=1)

        # Build set of relevant cities for geographic filtering
        relevant_cities = set(cities_set)
        relevant_cities.add(self.HOME_CITY)  # Home city is always relevant

        for inv in support_invoices:
            # Skip if already used in another trip
            if inv in trip_invoices:
                continue

            # First check: must be within date range
            if not (trip_start <= inv.date <= trip_end):
                continue

            # Second check: geographic relevance OR date proximity
            # Only include if the invoice is related to trip cities or dates
            is_geographically_relevant = False

            if inv.invoice_type in ["接送机", "打车"]:
                # For transfers and taxi, match by date proximity to journeys
                # OR by geographic relevance if route info is available
                origin_city = self._normalize_city(inv.origin) if inv.origin else None
                dest_city = self._normalize_city(inv.destination) if inv.destination else None

                # First, try geographic matching if route info is available
                if origin_city and origin_city in relevant_cities:
                    is_geographically_relevant = True
                elif dest_city and dest_city in relevant_cities:
                    is_geographically_relevant = True
                else:
                    # No route info or no geographic match - try date matching
                    # Match if within 1 day of any journey in this trip
                    for journey in chain:
                        date_diff = abs((inv.date - journey.date).days)
                        if date_diff <= 1:
                            is_geographically_relevant = True
                            break

            elif inv.invoice_type in ["住宿", "餐饮", "其他"]:
                # For hotels/dining/others, be more permissive if within date range
                # Only include if same day as a journey in this trip
                for journey in chain:
                    if inv.date == journey.date:
                        is_geographically_relevant = True
                        break

            if is_geographically_relevant:
                trip_invoices.append(inv)

        # Recalculate end_date based on ALL matched invoices
        if trip_invoices:
            end_date = max(inv.date for inv in trip_invoices)

        # Create Trip object
        return Trip(
            trip_id="",  # Will be set by caller
            traveler=traveler,
            start_date=start_date,
            end_date=end_date,
            destination=trip_name,
            invoices=trip_invoices,
            cities=cities if complete else []
        )

    def generate_trip_directories(self, output_dir: str = "trips") -> List[Trip]:
        """
        Generate directory structure for trips and organize files.

        Directory structure:
        trips/
          {traveler}/
            {start_date}_{end_date}_{cities}/
              {date}_{type}_{details}.pdf

        Args:
            output_dir: Base output directory

        Returns:
            List of Trip objects
        """
        trips = self.group_by_trip()
        base_dir = Path(output_dir)
        import shutil

        # Preserve existing non-invoice files in base directory (like 报销单.docx)
        preserved_files = {}
        if base_dir.exists():
            for file in base_dir.iterdir():
                if file.is_file() and not file.name.endswith('.md'):
                    # Preserve non-markdown files (like .docx templates)
                    preserved_files[file.name] = file
                    logger.info(f"Preserving existing file: {file.name}")

        for trip in trips:
            # Create trip directory with format: {start_date}_{end_date}_{cities}
            start_str = trip.start_date.strftime('%Y%m%d')
            end_str = trip.end_date.strftime('%Y%m%d')
            cities_str = '-'.join(trip.cities) if trip.cities else trip.destination
            trip_dir_name = f"{start_str}_{end_str}_{cities_str}"
            trip_dir = base_dir / trip.traveler / trip_dir_name

            # Preserve existing non-invoice files in trip directory
            preserved_trip_files = {}
            if trip_dir.exists():
                for file in trip_dir.iterdir():
                    if file.is_file() and not file.name.endswith('.pdf'):
                        # Preserve non-PDF files (like .docx, .md templates)
                        preserved_trip_files[file.name] = file
                        logger.info(f"Preserving existing file in trip: {file.name}")

            trip_dir.mkdir(parents=True, exist_ok=True)

            # Restore preserved files
            for name, src_file in preserved_trip_files.items():
                try:
                    shutil.copy2(src_file, trip_dir / name)
                    logger.info(f"Restored preserved file: {name}")
                except Exception as e:
                    logger.warning(f"Failed to restore {name}: {e}")

            # All files go directly into trip directory (no subdirectories)
            for inv in trip.invoices:
                target_path = trip_dir / inv.filename

                # Copy file (using shutil to avoid modifying source)
                import shutil
                try:
                    shutil.copy2(inv.filepath, target_path)
                    logger.info(f"Organized: {inv.filename} -> {trip_dir_name}/")
                except Exception as e:
                    logger.error(f"Failed to copy {inv.filename}: {e}")

            # Copy transfer files (all related invoices for each transfer)
            if trip.departure_transfer:
                for transfer_inv in trip.departure_transfer.invoices:
                    target_path = trip_dir / transfer_inv.filename
                    import shutil
                    try:
                        shutil.copy2(transfer_inv.filepath, target_path)
                        logger.info(f"Organized: {transfer_inv.filename} -> {trip_dir_name}/")
                    except Exception as e:
                        logger.error(f"Failed to copy {transfer_inv.filename}: {e}")

            if trip.return_transfer:
                for transfer_inv in trip.return_transfer.invoices:
                    target_path = trip_dir / transfer_inv.filename
                    try:
                        shutil.copy2(transfer_inv.filepath, target_path)
                        logger.info(f"Organized: {transfer_inv.filename} -> {trip_dir_name}/")
                    except Exception as e:
                        logger.error(f"Failed to copy {transfer_inv.filename}: {e}")

        # Handle unclassified taxi invoices - create "普通打车" folder
        # Track all used invoice filepaths
        used_invoice_paths = set()
        for trip in trips:
            for inv in trip.invoices:
                used_invoice_paths.add(inv.filepath)
            if trip.departure_transfer:
                for transfer_inv in trip.departure_transfer.invoices:
                    used_invoice_paths.add(transfer_inv.filepath)
            if trip.return_transfer:
                for transfer_inv in trip.return_transfer.invoices:
                    used_invoice_paths.add(transfer_inv.filepath)

        # Find unclassified taxi invoices by traveler
        all_invoices = self._collect_invoices()
        unclassified_taxi = defaultdict(list)  # traveler -> list of Invoice

        for inv in all_invoices:
            if inv.invoice_type == "打车" and inv.filepath not in used_invoice_paths:
                if inv.traveler:
                    unclassified_taxi[inv.traveler].append(inv)

        # Create "普通打车" folders for each traveler
        for traveler, taxi_invoices in unclassified_taxi.items():
            if taxi_invoices:
                taxi_dir = base_dir / traveler / "普通打车"
                taxi_dir.mkdir(parents=True, exist_ok=True)

                for inv in taxi_invoices:
                    target_path = taxi_dir / inv.filename
                    try:
                        shutil.copy2(inv.filepath, target_path)
                        logger.info(f"Organized unclassified taxi: {inv.filename} -> 普通打车/")
                    except Exception as e:
                        logger.error(f"Failed to copy {inv.filename}: {e}")

                logger.info(f"Created 普通打车 folder for {traveler} with {len(taxi_invoices)} invoices")

        # Generate trip summary (but preserve existing README.md if it has custom content)
        readme_path = base_dir / "README.md"
        if readme_path.exists():
            # Check if existing README has custom content beyond auto-generated header
            with open(readme_path, 'r', encoding='utf-8') as f:
                existing_content = f.read()
            # Only preserve if it doesn't look like our auto-generated format
            if '出差旅程汇总' not in existing_content or '报销单' in existing_content:
                logger.info("Preserving existing README.md with custom content")
                # Save existing README with a different name
                shutil.copy2(readme_path, base_dir / "README_old.md")
        self._generate_trip_summary(trips, readme_path, unclassified_taxi)

        # Restore preserved files to base directory
        for name, src_file in preserved_files.items():
            try:
                shutil.copy2(src_file, base_dir / name)
                logger.info(f"Restored preserved file to base: {name}")
            except Exception as e:
                logger.warning(f"Failed to restore {name}: {e}")

        return trips

    def _generate_trip_summary(self, trips: List[Trip], output_path: Path,
                               unclassified_taxi: Dict[str, List['Invoice']] = None):
        """Generate a summary markdown file for all trips."""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# 出差旅程汇总\n\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n")

            # Group by traveler
            by_traveler = defaultdict(list)
            for trip in trips:
                by_traveler[trip.traveler].append(trip)

            for traveler in sorted(by_traveler.keys()):
                f.write(f"## {traveler}\n\n")

                for trip in by_traveler[traveler]:
                    f.write(f"### {trip.destination}之行\n")
                    f.write(f"- **时间**: {trip.start_date} 至 {trip.end_date}\n")
                    f.write(f"- **地点**: {trip.destination}\n")
                    f.write(f"- **单据数**: {len(trip.invoices)} 张\n\n")

                    # List invoices
                    f.write("**单据明细**:\n\n")

                    # Group by category
                    departure_invoices = []
                    return_invoices_list = []
                    activity_invoices = []

                    # Add transfers first (all invoices from TripTransfer)
                    if trip.departure_transfer:
                        departure_invoices.extend(trip.departure_transfer.invoices)
                    if trip.return_transfer:
                        return_invoices_list.extend(trip.return_transfer.invoices)

                    for inv in trip.invoices:
                        # Skip transfers as they're already added
                        # Check if this invoice is in any transfer list
                        skip = False
                        if trip.departure_transfer:
                            if any(t.filepath == inv.filepath for t in trip.departure_transfer.invoices):
                                skip = True
                        if trip.return_transfer and not skip:
                            if any(t.filepath == inv.filepath for t in trip.return_transfer.invoices):
                                skip = True

                        if skip:
                            continue
                        elif inv.invoice_type in ["机票", "火车"]:
                            if inv.origin and self.HOME_CITY in inv.origin:
                                departure_invoices.append(inv)
                            elif inv.destination and self.HOME_CITY in inv.destination:
                                return_invoices_list.append(inv)
                            else:
                                # Intermediate flights
                                activity_invoices.append(inv)
                        else:
                            activity_invoices.append(inv)

                    if departure_invoices:
                        f.write("**出发**:\n")
                        for inv in departure_invoices:
                            f.write(f"- {inv.date} {inv.invoice_type}: {inv.origin or ''} -> {inv.destination or ''} ({inv.amount}元)\n")
                        f.write("\n")

                    if activity_invoices:
                        f.write("**行程**:\n")
                        for inv in activity_invoices:
                            desc = f"{inv.origin or ''} -> {inv.destination or ''}" if inv.origin or inv.destination else inv.invoice_type
                            f.write(f"- {inv.date} {inv.invoice_type}: {desc} ({inv.amount}元)\n")
                        f.write("\n")

                    if return_invoices_list:
                        f.write("**返回**:\n")
                        for inv in return_invoices_list:
                            f.write(f"- {inv.date} {inv.invoice_type}: {inv.origin or ''} -> {inv.destination or ''} ({inv.amount}元)\n")
                        f.write("\n")

                    f.write("---\n\n")

                # Add unclassified taxi section for this traveler
                if unclassified_taxi and traveler in unclassified_taxi:
                    taxi_invoices = unclassified_taxi[traveler]
                    if taxi_invoices:
                        f.write(f"### 普通打车\n")
                        f.write(f"- **单据数**: {len(taxi_invoices)} 张\n\n")
                        f.write("**单据明细**:\n\n")
                        for inv in sorted(taxi_invoices, key=lambda x: x.date):
                            f.write(f"- {inv.date} 打车: ({inv.amount}元)\n")
                        f.write("\n---\n\n")

    def generate_report(self, output_path: str = "trips_report.md"):
        """Generate a markdown report of all trips."""
        trips = self.group_by_trip()

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# 出差报告\n\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n")

            # Statistics
            f.write("## 统计摘要\n\n")
            f.write(f"- **总出差次数**: {len(trips)} 次\n")

            # By destination
            destinations = defaultdict(int)
            # By traveler
            travelers = defaultdict(int)
            total_amount = 0

            for trip in trips:
                destinations[trip.destination] += 1
                travelers[trip.traveler] += 1
                for inv in trip.invoices:
                    total_amount += inv.amount

            f.write(f"- **总金额**: ¥{total_amount:.2f} 元\n")
            # Filter out None destinations before sorting
            valid_destinations = [d for d in set(destinations.keys()) if d]
            f.write(f"- **目的地**: {', '.join(sorted(valid_destinations))}\n\n")

            f.write("### 出差人次\n\n")
            for traveler, count in sorted(travelers.items()):
                f.write(f"- **{traveler}**: {count} 次\n")

            f.write("\n### 目的地统计\n\n")
            for dest, count in sorted(destinations.items(), key=lambda x: -x[1]):
                f.write(f"- **{dest}**: {count} 次\n")

            f.write("\n---\n\n")

            # Detailed trips
            f.write("## 出差明细\n\n")

            for i, trip in enumerate(trips, 1):
                f.write(f"### {i}. {trip.traveler} - {trip.destination}之行\n")
                f.write(f"- **时间**: {trip.start_date} 至 {trip.end_date}\n")
                f.write(f"- **单据**: {len(trip.invoices)} 张\n")

                # Calculate total amount for this trip
                trip_amount = sum(inv.amount for inv in trip.invoices)
                f.write(f"- **金额**: ¥{trip_amount:.2f} 元\n\n")

        logger.info(f"Report generated: {output_path}")
        return trips


def group_trips(invoices_dir: str = "invoices", output_dir: str = "trips"):
    """
    Convenience function to group invoices into trips and organize files.

    Args:
        invoices_dir: Directory containing invoices
        output_dir: Output directory for organized trips
    """
    grouper = TripGrouper(invoices_dir)
    trips = grouper.generate_trip_directories(output_dir)

    logger.info(f"Grouped into {len(trips)} trips")
    logger.info(f"Output directory: {output_dir}")

    return trips
