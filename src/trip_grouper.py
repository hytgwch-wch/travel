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

        Filename format: {date}_{type}_{origin}_{destination}_{amount}_{traveler}_{doc_type}.pdf
        Example: 2026-02-10_机票_杭州_青岛_1065.00_王春晖.pdf
                 2026-02-02_接送机_紫金西苑-北门_萧山国际机场_T3_125.00_王春晖_行程单.pdf
        """
        name = filepath.stem

        # Parse filename
        parts = name.split('_')

        if len(parts) < 6:
            logger.warning(f"Cannot parse filename: {name}")
            return None

        try:
            # Date
            date_str = parts[0]
            invoice_date = datetime.strptime(date_str, "%Y-%m-%d").date()

            # Type
            invoice_type = parts[1]

            # Origin and destination (for flights/trains)
            origin = None
            destination = None
            route_start_idx = 2

            # Check if it's airport transfer with route info
            if invoice_type == "接送机":
                # Find the destination (airport)
                # Route format: 起点_终点_机场_航站楼
                for i in range(2, len(parts)):
                    if "国际机场" in parts[i] or "机场" in parts[i]:
                        # Extract route from start to airport
                        route_parts = parts[2:i+1]
                        origin = "_".join(route_parts) if route_parts else None
                        destination = "_".join(parts[i:i+2]) if i+1 < len(parts) else parts[i]
                        route_start_idx = i + 1
                        break
            elif invoice_type in ["机票", "火车"]:
                if len(parts) > 4:
                    origin = parts[2]
                    dest_match = re.match(r'([\d.]+)', parts[3])
                    if dest_match:
                        # Parts[3] might be amount, check if there's a proper destination
                        for i in range(3, min(6, len(parts))):
                            part = parts[i]
                            if re.match(r'^[\u4e00-\u9fa5]+$', part) and part not in ["元", "行程单", "发票"]:
                                destination = part
                                break
                    else:
                        destination = parts[3]

            # Amount
            amount = 0.0
            for i in range(route_start_idx, len(parts)):
                amount_match = re.match(r'(\d+\.\d{2})', parts[i])
                if amount_match:
                    amount = float(amount_match.group(1))
                    # Traveler is right after amount
                    if i + 1 < len(parts):
                        traveler = parts[i + 1]
                        # Check for document type suffix
                        if i + 2 < len(parts) and parts[i + 2] in ["行程单", "发票"]:
                            doc_type = parts[i + 2]
                        else:
                            doc_type = ""
                        break
            else:
                # No amount found, try to extract traveler from remaining parts
                for i in range(len(parts) - 1, -1, -1):
                    part = parts[i]
                    if part not in ["行程单", "发票", "pdf"] and not re.match(r'\d+\.\d{2}', part):
                        traveler = part
                        break
                doc_type = ""

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
    invoice: Invoice
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

        # Group by traveler
        by_traveler = defaultdict(list)
        for inv in invoices:
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
            if inv:
                invoices.append(inv)

        logger.info(f"Collected {len(invoices)} invoices")
        return invoices

    def _find_trips_for_traveler(self, traveler: str, invoices: List[Invoice]) -> List[Trip]:
        """
        Find complete trips for a single traveler.

        Args:
            traveler: Traveler name
            invoices: Sorted list of invoices for this traveler

        Returns:
            List of Trip objects
        """
        trips = []
        current_trip_invoices = []
        trip_start_date = None
        destination = None

        # Match transfers with their associated flight/train dates
        transfers = self._match_transfers(invoices)

        i = 0
        while i < len(invoices):
            inv = invoices[i]

            # Check if this is a departure from home
            if self._is_departure_from_home(inv):
                # Start a new trip
                if current_trip_invoices:
                    # Close previous trip
                    trip = self._create_trip(traveler, trip_start_date, destination,
                                             current_trip_invoices, transfers)
                    if trip:
                        trips.append(trip)

                # Start new trip
                trip_start_date = inv.date
                destination = inv.destination or self._extract_city_from_route(inv)
                current_trip_invoices = [inv]

            # Check if this is a return to home
            elif self._is_return_to_home(inv):
                # Add to current trip and close it
                current_trip_invoices.append(inv)

                trip = self._create_trip(traveler, trip_start_date, destination,
                                         current_trip_invoices, transfers)
                if trip:
                    trips.append(trip)

                current_trip_invoices = []
                trip_start_date = None
                destination = None

            # Other invoices during trip
            else:
                if current_trip_invoices:
                    current_trip_invoices.append(inv)
                else:
                    # Orphan invoice (no clear trip context)
                    logger.debug(f"Orphan invoice: {inv}")

            i += 1

        # Handle any remaining open trip
        if current_trip_invoices:
            trip = self._create_trip(traveler, trip_start_date, destination,
                                     current_trip_invoices, transfers)
            if trip:
                trips.append(trip)

        return trips

    def _match_transfers(self, invoices: List[Invoice]) -> Dict[Tuple[date, str], TripTransfer]:
        """
        Match airport transfer invoices with their associated flight/train dates.

        Args:
            invoices: List of invoices

        Returns:
            Dict mapping (date, direction) to TripTransfer info
        """
        transfers = {}
        transfer_invoices = [inv for inv in invoices if inv.invoice_type == "接送机"]

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

                transfers[(closest_invoice.date, direction)] = TripTransfer(
                    invoice=transfer_inv,
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
        """Extract destination city from route."""
        if inv.destination:
            # Extract city name (before special characters)
            city_match = re.match(r'([\u4e00-\u9fa5]{2})', inv.destination)
            if city_match:
                return city_match.group(1)
        return "未知"

    def _create_trip(self, traveler: str, start_date: date, destination: str,
                     invoices: List[Invoice], transfers: Dict[Tuple[date, str], TripTransfer]) -> Optional[Trip]:
        """Create a Trip object with associated transfers."""
        if not invoices:
            return None

        # Calculate end date from latest invoice
        end_date = max(inv.date for inv in invoices)

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
                        departure_transfer = transfer.invoice
                    elif direction == "返回":
                        return_transfer = transfer.invoice

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

        for trip in trips:
            # Create trip directory with format: {start_date}_{end_date}_{cities}
            start_str = trip.start_date.strftime('%Y%m%d')
            end_str = trip.end_date.strftime('%Y%m%d')
            cities_str = '-'.join(trip.cities) if trip.cities else trip.destination
            trip_dir_name = f"{start_str}_{end_str}_{cities_str}"
            trip_dir = base_dir / trip.traveler / trip_dir_name
            trip_dir.mkdir(parents=True, exist_ok=True)

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

            # Copy transfer files
            if trip.departure_transfer:
                target_path = trip_dir / trip.departure_transfer.filename
                import shutil
                try:
                    shutil.copy2(trip.departure_transfer.filepath, target_path)
                    logger.info(f"Organized: {trip.departure_transfer.filename} -> {trip_dir_name}/")
                except Exception as e:
                    logger.error(f"Failed to copy {trip.departure_transfer.filename}: {e}")

            if trip.return_transfer:
                target_path = trip_dir / trip.return_transfer.filename
                import shutil
                try:
                    shutil.copy2(trip.return_transfer.filepath, target_path)
                    logger.info(f"Organized: {trip.return_transfer.filename} -> {trip_dir_name}/")
                except Exception as e:
                    logger.error(f"Failed to copy {trip.return_transfer.filename}: {e}")

        # Generate trip summary
        self._generate_trip_summary(trips, base_dir / "README.md")

        return trips

    def _generate_trip_summary(self, trips: List[Trip], output_path: Path):
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

                    # Add transfers first
                    if trip.departure_transfer:
                        departure_invoices.append(trip.departure_transfer)
                    if trip.return_transfer:
                        return_invoices_list.append(trip.return_transfer)

                    for inv in trip.invoices:
                        # Skip transfers as they're already added
                        if inv == trip.departure_transfer or inv == trip.return_transfer:
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
            f.write(f"- **目的地**: {', '.join(sorted(set(destinations.keys())))}\n\n")

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
