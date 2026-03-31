"""
Intelligent recognition enhancement module.

Provides smart features based on historical data:
- Learning from historical invoice patterns
- Smart suggestions for invoice categorization
- Automatic location association
- Similar invoice detection
"""

import re
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict, Counter
from dataclasses import dataclass
from difflib import SequenceMatcher

from loguru import logger


@dataclass
class LocationPattern:
    """Learned location pattern from historical data."""
    origin: str
    destination: str
    invoice_type: str  # 机票, 火车, etc.
    frequency: int
    avg_amount: float
    common_dates: List[date]


@dataclass
class InvoiceSuggestion:
    """Suggestion for invoice categorization."""
    invoice_path: str
    suggested_type: Optional[str]
    suggested_origin: Optional[str]
    suggested_destination: Optional[str]
    suggested_date: Optional[date]
    confidence: float
    reason: str


class SmartInvoiceLearner:
    """
    Learn patterns from historical invoice data for smarter recognition.
    """

    def __init__(self, invoices_dir: str = "invoices"):
        """Initialize learner.

        Args:
            invoices_dir: Directory containing processed invoices
        """
        self.invoices_dir = Path(invoices_dir)
        self.location_patterns: List[LocationPattern] = []
        self.date_patterns: Dict[str, List[date]] = defaultdict(list)
        self.amount_patterns: Dict[str, List[float]] = defaultdict(list)

    def learn_from_history(self):
        """Analyze historical invoice data to learn patterns."""
        logger.info("Starting to learn from historical invoice data...")

        self._learn_location_patterns()
        self._learn_date_patterns()
        self._learn_amount_patterns()

        logger.info(f"Learning complete. Learned {len(self.location_patterns)} location patterns")

    def _learn_location_patterns(self):
        """Learn common routes from historical data."""
        route_counter = defaultdict(lambda: {'count': 0, 'amounts': []})

        for pdf_file in self.invoices_dir.rglob("*.pdf"):
            filename = pdf_file.name
            info = self._parse_filename_info(filename)

            if info and info.get('origin') and info.get('destination'):
                key = (info['type'], info['origin'], info['destination'])
                route_counter[key]['count'] += 1
                if info.get('amount'):
                    route_counter[key]['amounts'].append(info['amount'])

        # Convert to patterns
        self.location_patterns = []
        for (type_name, origin, dest), data in route_counter.items():
            if data['count'] >= 1:  # Only keep patterns seen at least once
                avg_amount = sum(data['amounts']) / len(data['amounts']) if data['amounts'] else 0
                self.location_patterns.append(LocationPattern(
                    origin=origin,
                    destination=dest,
                    invoice_type=type_name,
                    frequency=data['count'],
                    avg_amount=avg_amount,
                    common_dates=[]
                ))

        # Sort by frequency
        self.location_patterns.sort(key=lambda x: x.frequency, reverse=True)

    def _learn_date_patterns(self):
        """Learn common travel dates by route."""
        for pdf_file in self.invoices_dir.rglob("*.pdf"):
            filename = pdf_file.name
            info = self._parse_filename_info(filename)

            if info and info.get('date'):
                route_key = f"{info.get('type', '')}_{info.get('origin', '')}_{info.get('destination', '')}"
                self.date_patterns[route_key].append(info['date'])

    def _learn_amount_patterns(self):
        """Learn typical amount ranges for routes."""
        for pdf_file in self.invoices_dir.rglob("*.pdf"):
            filename = pdf_file.name
            info = self._parse_filename_info(filename)

            if info and info.get('amount'):
                route_key = f"{info.get('type', '')}_{info.get('origin', '')}_{info.get('destination', '')}"
                self.amount_patterns[route_key].append(info['amount'])

    def _parse_filename_info(self, filename: str) -> Optional[Dict]:
        """Parse basic info from filename."""
        info = {}

        # Try to extract date
        date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', filename)
        if date_match:
            try:
                info['date'] = date(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
            except ValueError:
                pass

        # Try to extract amount
        amount_match = re.search(r'(\d+\.\d{2})', filename)
        if amount_match:
            info['amount'] = float(amount_match.group(1))

        # Try to extract invoice type
        for type_name in ['机票', '火车', '打车', '接送机', '住宿', '餐饮']:
            if type_name in filename:
                info['type'] = type_name
                break
        else:
            info['type'] = '其他'

        # Try to extract origin/destination (simplified)
        parts = filename.replace('.pdf', '').split('_')
        if len(parts) >= 4:
            if info['type'] in ['机票', '火车']:
                info['origin'] = parts[2] if len(parts) > 2 else None
                info['destination'] = parts[3] if len(parts) > 3 else None

        return info if info else None

    def suggest_categorization(self, invoice_path: str) -> InvoiceSuggestion:
        """
        Suggest categorization for an uncategorized invoice.

        Args:
            invoice_path: Path to the invoice file

        Returns:
            Suggestion with type, route, date, and confidence
        """
        pdf_path = Path(invoice_path)
        filename = pdf_path.name

        # Get basic info from filename
        info = self._parse_filename_info(filename) or {}

        suggestions = []

        # Suggest based on similar routes
        if info.get('origin') and info.get('destination'):
            for pattern in self.location_patterns[:10]:  # Check top 10 patterns
                similarity = self._calculate_route_similarity(
                    info['origin'], info['destination'],
                    pattern.origin, pattern.destination
                )
                if similarity > 0.5:
                    suggestions.append({
                        'type': pattern.invoice_type,
                        'confidence': similarity,
                        'reason': f"相似路线 ({pattern.origin}→{pattern.destination}, {pattern.frequency}次历史)"
                    })

        # Suggest based on amount patterns
        if info.get('amount'):
            route_key = f"{info.get('type', '')}_{info.get('origin', '')}_{info.get('destination', '')}"
            if route_key in self.amount_patterns:
                historical_amounts = self.amount_patterns[route_key]
                # Check if amount is in typical range
                if historical_amounts:
                    avg = sum(historical_amounts) / len(historical_amounts)
                    if abs(info['amount'] - avg) / avg < 0.5:  # Within 50%
                        suggestions.append({
                            'type': info.get('type'),
                            'confidence': 0.8,
                            'reason': f"金额符合历史模式 (历史平均: {avg:.2f})"
                        })

        # Sort by confidence
        suggestions.sort(key=lambda x: x['confidence'], reverse=True)

        if suggestions:
            best = suggestions[0]
            return InvoiceSuggestion(
                invoice_path=invoice_path,
                suggested_type=best.get('type'),
                suggested_origin=info.get('origin'),
                suggested_destination=info.get('destination'),
                suggested_date=info.get('date'),
                confidence=best['confidence'],
                reason=best['reason']
            )

        return InvoiceSuggestion(
            invoice_path=invoice_path,
            suggested_type=None,
            suggested_origin=None,
            suggested_destination=None,
            suggested_date=None,
            confidence=0.0,
            reason="无匹配的历史模式"
        )

    def _calculate_route_similarity(self, origin1: str, dest1: str, origin2: str, dest2: str) -> float:
        """Calculate similarity between two routes."""
        if not origin1 or not dest1 or not origin2 or not dest2:
            return 0.0

        # Check for exact match
        if origin1 == origin2 and dest1 == dest2:
            return 1.0

        # Check for partial match
        origin_sim = SequenceMatcher(None, origin1, origin2).ratio()
        dest_sim = SequenceMatcher(None, dest1, dest2).ratio()

        return (origin_sim + dest_sim) / 2

    def find_similar_invoices(self, invoice_path: str, limit: int = 5) -> List[Tuple[str, float]]:
        """
        Find historically similar invoices.

        Args:
            invoice_path: Path to the invoice file
            limit: Maximum number of similar invoices to return

        Returns:
            List of (similar_invoice_path, similarity_score) tuples
        """
        pdf_path = Path(invoice_path)
        filename = pdf_path.name

        similarities = []

        for hist_file in self.invoices_dir.rglob("*.pdf"):
            if hist_file == pdf_path:
                continue

            sim = self._calculate_filename_similarity(filename, hist_file.name)
            if sim > 0.3:  # Threshold for similarity
                similarities.append((str(hist_file.relative_to(self.invoices_dir)), sim))

        # Sort by similarity and return top N
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:limit]

    def _calculate_filename_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two filenames."""
        return SequenceMatcher(None, name1, name2).ratio()

    def suggest_trip_association(self, invoice_path: str, existing_trips: List[Dict]) -> Optional[Dict]:
        """
        Suggest which trip an uncategorized invoice belongs to.

        Args:
            invoice_path: Path to the invoice file
            existing_trips: List of trip dictionaries with 'destination', 'start_date', 'end_date'

        Returns:
            Best matching trip or None
        """
        pdf_path = Path(invoice_path)
        filename = pdf_path.name
        info = self._parse_filename_info(filename)

        if not info or not info.get('date'):
            return None

        invoice_date = info['date']

        # Find trips with date proximity
        candidates = []
        for trip in existing_trips:
            try:
                start_date = datetime.strptime(trip['start_date'], "%Y%m%d").date()
                end_date = datetime.strptime(trip['end_date'], "%Y%m%d").date()

                # Calculate date distance
                days_before = (invoice_date - start_date).days if invoice_date >= start_date else -999
                days_after = (end_date - invoice_date).days if invoice_date <= end_date else -999

                if days_before >= -3 and days_after >= -3:  # Within 3 days
                    # Check destination similarity
                    dest_sim = 0
                    if trip.get('destination') and info.get('origin'):
                        dest_sim = SequenceMatcher(None, trip['destination'], info['origin']).ratio()

                    candidates.append({
                        'trip': trip,
                        'date_proximity': abs(min(days_before, days_after, key=abs)),
                        'destination_similarity': dest_sim
                    })
            except (ValueError, KeyError):
                continue

        if not candidates:
            return None

        # Sort by combined score (date proximity + destination similarity)
        candidates.sort(key=lambda x: x['date_proximity'] - x['destination_similarity'] * 10)

        best = candidates[0]
        return {
            'trip': best['trip'],
            'confidence': 1.0 - (best['date_proximity'] / 10),
            'reason': f"日期接近 (相差{best['date_proximity']}天)"
        }


class LocationAssociator:
    """
    Automatically associate invoice locations with trip destinations.

    Helps identify which trips an invoice belongs to based on location patterns.
    """

    def __init__(self):
        """Initialize location associator."""
        self.city_aliases: Dict[str, Set[str]] = {
            '杭州': {'杭州东', '杭州西', '杭州南', '萧山', '临平'},
            '北京': {'北京南', '北京西', '北京北', '首都', '大兴'},
            '上海': {'上海虹桥', '上海南', '上海西', '浦东'},
            '南京': {'南京南', '南京东', '南京西'},
            '深圳': {'深圳北', '深圳南', '深圳东'},
            '广州': {'广州南', '广州东', '广州北'},
            '武汉': {'武汉', '武昌', '汉口', '汉阳'},
            '成都': {'成都东', '成都南', '成都西'},
            '重庆': {'重庆北', '重庆南', '重庆西'},
            '西安': {'西安北', '西安南'},
            '天津': {'天津西', '天津南', '天津北'},
            '苏州': {'苏州北', '苏州南', '苏州园区'},
            '无锡': {'无锡东', '无锡新区'},
            '宁波': {'宁波站', '宁波东'},
            '青岛': {'青岛北', '青岛西', '青岛东'},
            '大连': {'大连北', '大连南'},
            '沈阳': {'沈阳北', '沈阳南'},
            '长沙': {'长沙南', '长沙西'},
            '郑州': {'郑州东', '郑州西'},
        }

    def normalize_city(self, location: str) -> str:
        """
        Normalize location name to standard city name.

        Args:
            location: Location string (may include station suffix)

        Returns:
            Normalized city name
        """
        if not location:
            return location

        # Remove common suffixes
        for suffix in ['东站', '西站', '南站', '北站', '站', '机场', '国际机场', 'T3', 'T2', 'T1']:
            if location.endswith(suffix):
                location = location[:-len(suffix)]
                break

        # Check aliases
        for city, aliases in self.city_aliases.items():
            if location in aliases:
                return city

        return location

    def calculate_distance(self, loc1: str, loc2: str) -> int:
        """
        Calculate conceptual distance between two locations.

        Returns 0 if same city, 1 if nearby/in same province, 2 if far.
        """
        norm1 = self.normalize_city(loc1 or '')
        norm2 = self.normalize_city(loc2 or '')

        if norm1 == norm2:
            return 0
        if (norm1 in self.city_aliases and norm2 in self.city_aliases[norm1]) or \
           (norm2 in self.city_aliases and norm1 in self.city_aliases[norm2]):
            return 1
        return 2

    def find_nearby_locations(self, location: str, radius: int = 2) -> List[str]:
        """
        Find locations within a certain distance.

        Args:
            location: Center location
            radius: Maximum distance (0=same city, 1=nearby, 2=far)

        Returns:
            List of nearby location names
        """
        nearby = []
        norm_location = self.normalize_city(location)

        for city, aliases in self.city_aliases.items():
            # Add the main city
            if self.calculate_distance(norm_location, city) <= radius:
                nearby.append(city)

            # Add aliases
            for alias in aliases:
                if self.calculate_distance(norm_location, alias) <= radius:
                    nearby.append(alias)

        return nearby

    def suggest_trip_destinations(self, origin: str, destination: str) -> List[str]:
        """
        Suggest possible trip destinations based on route.

        Args:
            origin: Starting location
            destination: Ending location

        Returns:
            List of suggested destination names for trip folder
        """
        norm_origin = self.normalize_city(origin)
        norm_dest = self.normalize_city(destination)

        suggestions = []

        # Direct route
        if norm_origin and norm_dest:
            if norm_origin != norm_dest:
                suggestions.append(f"{norm_origin}-{norm_dest}")
            else:
                suggestions.append(norm_dest)

        # Multi-city possibilities
        nearby_dest = self.find_nearby_locations(destination, radius=1)
        for loc in nearby_dest[:3]:  # Top 3
            if loc != norm_dest:
                suggestions.append(f"{norm_origin}-{loc}")

        return list(set(suggestions))[:5]  # Return unique suggestions


class SmartTripGrouper:
    """
    Enhanced trip grouping with intelligent suggestions.
    """

    def __init__(self, invoices_dir: str = "invoices"):
        """Initialize smart trip grouper.

        Args:
            invoices_dir: Directory containing processed invoices
        """
        self.invoices_dir = Path(invoices_dir)
        self.learner = SmartInvoiceLearner(invoices_dir)
        self.associator = LocationAssociator()

    def learn_and_suggest(self) -> Dict[str, List[InvoiceSuggestion]]:
        """
        Learn from history and generate suggestions for uncategorized invoices.

        Returns:
            Dictionary mapping invoice paths to suggestions
        """
        # First, learn from existing data
        self.learner.learn_from_history()

        suggestions = {}

        # Find invoices that might need suggestions
        # (e.g., invoices in "普通打车" folder or uncategorized files)
        trips_dir = Path("trips")
        if trips_dir.exists():
            for traveler_dir in trips_dir.iterdir():
                if not traveler_dir.is_dir():
                    continue

                # Check "普通打车" folder
                unclassified_dir = traveler_dir / "普通打车"
                if unclassified_dir.exists():
                    for pdf_file in unclassified_dir.glob("*.pdf"):
                        suggestion = self.learner.suggest_categorization(str(pdf_file))
                        suggestions[str(pdf_file)] = suggestion

        return suggestions

    def auto_associate_invoices_to_trips(self) -> Dict[str, List[str]]:
        """
        Automatically suggest which trip each invoice belongs to.

        Returns:
            Dictionary mapping trip paths to lists of invoice paths
        """
        # Get existing trips
        trips = []
        trips_dir = Path("trips")
        if trips_dir.exists():
            for traveler_dir in trips_dir.iterdir():
                if not traveler_dir.is_dir():
                    continue

                for trip_dir in traveler_dir.iterdir():
                    if not trip_dir.is_dir() or trip_dir.name == "普通打车":
                        continue

                    parts = trip_dir.name.split('_')
                    if len(parts) >= 3:
                        trips.append({
                            'path': str(trip_dir.relative_to(trips_dir)),
                            'destination': parts[2],
                            'start_date': parts[0],
                            'end_date': parts[1]
                        })

        # Find unassociated invoices
        associations = defaultdict(list)

        for traveler_dir in trips_dir.iterdir():
            if not traveler_dir.is_dir():
                continue

            unclassified_dir = traveler_dir / "普通打车"
            if unclassified_dir.exists():
                for pdf_file in unclassified_dir.glob("*.pdf"):
                    association = self.learner.suggest_trip_association(str(pdf_file), trips)
                    if association and association['confidence'] > 0.5:
                        trip_path = str(traveler_dir / association['trip']['path'])
                        associations[trip_path].append(str(pdf_file))

        return dict(associations)


def generate_smart_suggestions_report(output_path: str = "reports/smart_suggestions.txt"):
    """
    Generate a report with smart categorization suggestions.

    Args:
        output_path: Path to save the report
    """
    grouper = SmartTripGrouper()
    suggestions = grouper.learn_and_suggest()

    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    output_file = reports_dir / "smart_suggestions.txt"

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("智能识别建议报告\n")
        f.write("=" * 60 + "\n\n")

        if not suggestions:
            f.write("暂无建议\n")
        else:
            for invoice_path, suggestion in suggestions.items():
                f.write(f"文件: {invoice_path}\n")
                f.write(f"  建议类型: {suggestion.suggested_type or '未确定'}\n")
                f.write(f"  建议出发地: {suggestion.suggested_origin or '未确定'}\n")
                f.write(f"  建议目的地: {suggestion.suggested_destination or '未确定'}\n")
                f.write(f"  置信度: {suggestion.confidence:.2%}\n")
                f.write(f"  理由: {suggestion.reason}\n")
                f.write("\n")

    logger.info(f"Smart suggestions report saved to {output_file}")
    return str(output_file)
