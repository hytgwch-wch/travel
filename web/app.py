"""
Flask Web Application for Travel Invoice System.

Provides a web interface for:
- Viewing processing records
- Manually triggering tasks
- Configuration management
- File review and management
"""

import os
import json
import shutil
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file
from werkzeug.utils import secure_filename

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import RecordDatabase
from src.scheduler import TaskScheduler
from src.config import get_config

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# Configuration
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
UPLOAD_FOLDER = Path('temp')
UPLOAD_FOLDER.mkdir(exist_ok=True)

# Initialize components
db = RecordDatabase()
scheduler = TaskScheduler()


# ============================================
# Routes - Dashboard
# ============================================

@app.route('/')
def index():
    """Dashboard home page."""
    # Get statistics
    stats = {
        'total_processed': db.get_count(),
        'today_processed': db.get_count_today(),
        'invoices_by_type': db.get_stats_by_type(),
        'recent_activity': db.get_recent_records(limit=10)
    }

    # Get trip folders
    trips_dir = Path('trips')
    trip_stats = []
    if trips_dir.exists():
        for traveler_dir in trips_dir.iterdir():
            if traveler_dir.is_dir() and not traveler_dir.name.startswith('.'):
                trip_count = sum(1 for d in traveler_dir.iterdir() if d.is_dir() and d.name != '普通打车')
                trip_stats.append({
                    'name': traveler_dir.name,
                    'trip_count': trip_count
                })

    return render_template('dashboard.html', stats=stats, trip_stats=trip_stats)


# ============================================
# Routes - Tasks
# ============================================

@app.route('/tasks')
def tasks():
    """Task management page."""
    return render_template('tasks.html')


@app.route('/api/tasks/run', methods=['POST'])
def api_run_task():
    """Run a single task execution."""
    try:
        result = scheduler.run_once()
        return jsonify({
            'success': True,
            'result': {
                'emails_processed': result.emails_processed,
                'files_downloaded': result.files_downloaded,
                'files_processed': result.files_processed,
                'errors': result.errors
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tasks/trips', methods=['POST'])
def api_generate_trips():
    """Generate trip groupings."""
    try:
        from src.trip_grouper import TripGrouper
        grouper = TripGrouper()
        trips = grouper.group_by_trip()
        grouper.generate_trip_directories(trips)
        return jsonify({
            'success': True,
            'trip_count': len(trips)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tasks/status')
def api_task_status():
    """Get current task status."""
    # This could check for running tasks
    return jsonify({
        'running': False,
        'last_run': db.get_last_run_time()
    })


@app.route('/api/tasks/sync-email', methods=['POST'])
def api_sync_email():
    """Sync new emails from IMAP server without processing."""
    try:
        db.connect()
        known_files = db.get_known_files()

        # Use scheduler's sync manager to download new files
        new_files = scheduler.sync_manager.sync_new_files(known_files, db=db)

        db.close()

        return jsonify({
            'success': True,
            'emails_checked': len(scheduler.sync_manager.downloaded_files_meta),
            'files_downloaded': len(new_files),
            'message': f'下载了 {len(new_files)} 个新文件'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# Routes - Records
# ============================================

@app.route('/records')
def records():
    """Processing records page."""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page

    records = db.get_records(limit=per_page, offset=offset)
    total = db.get_count()

    return render_template('records.html',
                         records=records,
                         page=page,
                         per_page=per_page,
                         total=total,
                         total_pages=(total + per_page - 1) // per_page)


@app.route('/api/records')
def api_records():
    """Get records as JSON."""
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    records = db.get_records(limit=limit, offset=offset)
    total = db.get_count()

    return jsonify({
        'records': [dict(r) for r in records],
        'total': total,
        'limit': limit,
        'offset': offset
    })


@app.route('/api/records/<int:record_id>')
def api_record_detail(record_id):
    """Get detail of a specific record."""
    record = db.get_record_by_id(record_id)
    if record:
        return jsonify(dict(record))
    return jsonify({'error': 'Record not found'}), 404


# ============================================
# Routes - Files
# ============================================

@app.route('/files')
def files():
    """File management page."""
    invoices_dir = Path('invoices')
    files_by_type = {}

    if invoices_dir.exists():
        for year_dir in invoices_dir.iterdir():
            if year_dir.is_dir():
                for type_dir in year_dir.iterdir():
                    if type_dir.is_dir():
                        files = list(type_dir.glob('*.pdf'))
                        type_name = type_dir.name
                        if type_name not in files_by_type:
                            files_by_type[type_name] = []
                        files_by_type[type_name].extend([
                            {'name': f.name, 'path': str(f), 'size': f.stat().st_size}
                            for f in files
                        ])

    return render_template('files.html', files_by_type=files_by_type)


@app.route('/api/files/upload', methods=['POST'])
def api_upload_file():
    """Upload a file for processing."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file:
        filename = secure_filename(file.filename)
        filepath = UPLOAD_FOLDER / filename
        file.save(filepath)

        # Trigger processing
        try:
            result = scheduler.process_single_file(str(filepath))
            return jsonify({
                'success': True,
                'result': result
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500


@app.route('/api/files/review')
def api_files_review():
    """Get files pending review."""
    # This could return files with low confidence or errors
    review_files = []

    invoices_dir = Path('invoices')
    if invoices_dir.exists():
        for pdf_file in invoices_dir.rglob('*.pdf'):
            # Check if file needs review (e.g., small size, recently added)
            if pdf_file.stat().st_size < 10000:  # Less than 10KB
                review_files.append({
                    'name': pdf_file.name,
                    'path': str(pdf_file.relative_to(invoices_dir)),
                    'size': pdf_file.stat().st_size,
                    'reason': '小文件（可能识别不完整）'
                })

    return jsonify({'files': review_files})


# ============================================
# Routes - Trips
# ============================================

@app.route('/trips')
def trips():
    """Trip management page."""
    trips_dir = Path('trips')
    trips_by_traveler = {}

    if trips_dir.exists():
        for traveler_dir in trips_dir.iterdir():
            if traveler_dir.is_dir() and not traveler_dir.name.startswith('.'):
                traveler_trips = []
                for trip_dir in traveler_dir.iterdir():
                    if trip_dir.is_dir() and trip_dir.name != '普通打车':
                        # Parse trip folder name
                        parts = trip_dir.name.split('_')
                        if len(parts) >= 3:
                            traveler_trips.append({
                                'name': trip_dir.name,
                                'start_date': parts[0],
                                'end_date': parts[1],
                                'destination': parts[2],
                                'invoice_count': len(list(trip_dir.glob('*.pdf')))
                            })
                traveler_trips.sort(key=lambda x: x['start_date'], reverse=True)
                trips_by_traveler[traveler_dir.name] = traveler_trips

    return render_template('trips.html', trips_by_traveler=trips_by_traveler)


@app.route('/api/trips/<path:trip_path>')
def api_trip_detail(trip_path):
    """Get detail of a specific trip."""
    trip_dir = Path('trips') / trip_path
    if not trip_dir.exists():
        return jsonify({'error': 'Trip not found'}), 404

    invoices = []
    for pdf_file in trip_dir.glob('*.pdf'):
        invoices.append({
            'name': pdf_file.name,
            'size': pdf_file.stat().st_size
        })

    # Check for README
    readme = trip_dir / 'README.md'
    readme_content = None
    if readme.exists():
        readme_content = readme.read_text(encoding='utf-8')

    return jsonify({
        'path': trip_path,
        'invoices': invoices,
        'readme': readme_content
    })


# ============================================
# Routes - Configuration
# ============================================

@app.route('/config')
def config():
    """Configuration page."""
    return render_template('config.html')


@app.route('/api/config')
def api_get_config():
    """Get current configuration."""
    config = get_config()
    return jsonify({
        'local_output_dir': config.local_output_dir,
        'default_traveler': config.default_traveler
    })


@app.route('/api/config', methods=['POST'])
def api_update_config():
    """Update configuration."""
    try:
        data = request.get_json()

        # Update config file (simplified for demo)
        # In production, you'd update the actual YAML files

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# Routes - Statistics
# ============================================

@app.route('/stats')
def stats():
    """Statistics page."""
    return render_template('stats.html')


@app.route('/api/stats')
def api_stats():
    """Get system statistics."""
    stats = {
        'total_processed': db.get_count(),
        'today_processed': db.get_count_today(),
        'by_type': db.get_stats_by_type(),
        'by_date': db.get_stats_by_date(days=30)
    }
    return jsonify(stats)


@app.route('/api/stats/monthly')
def api_monthly_stats():
    """Get monthly statistics for charts."""
    from src.statistics import InvoiceStatistics

    months = request.args.get('months', 12, type=int)
    stats_calculator = InvoiceStatistics()
    monthly_stats = stats_calculator.get_monthly_stats(months)

    return jsonify({
        'stats': [
            {
                'month': f"{s.year}-{s.month:02d}",
                'total_amount': s.total_amount,
                'invoice_count': s.invoice_count,
                'by_type': s.by_type
            }
            for s in monthly_stats
        ]
    })


@app.route('/api/stats/traveler')
def api_traveler_stats():
    """Get statistics by traveler."""
    from src.statistics import InvoiceStatistics

    stats_calculator = InvoiceStatistics()
    traveler_stats = stats_calculator.get_traveler_stats()

    return jsonify({
        'stats': [
            {
                'name': s.name,
                'total_amount': s.total_amount,
                'invoice_count': s.invoice_count,
                'trip_count': s.trip_count,
                'by_type': s.by_type
            }
            for s in traveler_stats
        ]
    })


@app.route('/api/stats/type')
def api_type_stats():
    """Get statistics by invoice type."""
    from src.statistics import InvoiceStatistics

    stats_calculator = InvoiceStatistics()
    type_stats = stats_calculator.get_type_stats()

    return jsonify({
        'stats': [
            {
                'type': s.type_name,
                'total_amount': s.total_amount,
                'invoice_count': s.invoice_count,
                'avg_amount': s.avg_amount
            }
            for s in type_stats
        ]
    })


@app.route('/api/stats/export')
def api_export_stats():
    """Export statistics as Excel file."""
    from src.statistics import ExcelReportGenerator

    report_type = request.args.get('type', 'comprehensive')
    months = request.args.get('months', 12, type=int)

    generator = ExcelReportGenerator()

    # Create reports directory
    reports_dir = Path('reports')
    reports_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    if report_type == 'monthly':
        output_path = reports_dir / f"月度统计_{timestamp}.xlsx"
        generator.create_monthly_report(str(output_path), months)
    elif report_type == 'traveler':
        output_path = reports_dir / f"出差人统计_{timestamp}.xlsx"
        generator.create_traveler_report(str(output_path))
    elif report_type == 'type':
        output_path = reports_dir / f"类型统计_{timestamp}.xlsx"
        generator.create_type_report(str(output_path))
    else:  # comprehensive
        output_path = reports_dir / f"综合统计_{timestamp}.xlsx"
        generator.create_comprehensive_report(str(output_path), months)

    return jsonify({
        'success': True,
        'file_path': str(output_path),
        'download_url': f'/api/stats/download?path={output_path.name}'
    })


@app.route('/api/stats/download')
def api_download_report():
    """Download generated report file."""
    filename = request.args.get('path')
    if not filename:
        return jsonify({'error': 'No file specified'}), 400

    file_path = Path('reports') / filename
    if not file_path.exists():
        return jsonify({'error': 'File not found'}), 404

    return send_file(str(file_path), as_attachment=True, download_name=filename)


# ============================================
# Routes - Smart Recognition
# ============================================

@app.route('/smart')
def smart():
    """Smart recognition features page."""
    return render_template('smart.html')


@app.route('/api/smart/learn', methods=['POST'])
def api_smart_learn():
    """Learn from historical invoice data."""
    from src.smart_recognition import SmartInvoiceLearner

    try:
        learner = SmartInvoiceLearner()
        learner.learn_from_history()

        return jsonify({
            'success': True,
            'message': f'学习完成，识别了 {len(learner.location_patterns)} 个路线模式'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/smart/suggestions')
def api_smart_suggestions():
    """Get smart categorization suggestions."""
    from src.smart_recognition import SmartTripGrouper

    try:
        grouper = SmartTripGrouper()
        suggestions = grouper.learn_and_suggest()

        result = []
        for invoice_path, suggestion in suggestions.items():
            result.append({
                'invoice': invoice_path,
                'suggested_type': suggestion.suggested_type,
                'suggested_origin': suggestion.suggested_origin,
                'suggested_destination': suggestion.suggested_destination,
                'confidence': suggestion.confidence,
                'reason': suggestion.reason
            })

        return jsonify({'suggestions': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/smart/associate')
def api_smart_associate():
    """Get automatic trip association suggestions."""
    from src.smart_recognition import SmartTripGrouper

    try:
        grouper = SmartTripGrouper()
        associations = grouper.auto_associate_invoices_to_trips()

        result = []
        for trip_path, invoice_paths in associations.items():
            result.append({
                'trip': trip_path,
                'invoices': invoice_paths,
                'count': len(invoice_paths)
            })

        return jsonify({'associations': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/smart/report', methods=['POST'])
def api_smart_report():
    """Generate smart suggestions report."""
    from src.smart_recognition import generate_smart_suggestions_report

    try:
        report_path = generate_smart_suggestions_report()

        # Read report content
        with open(report_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return jsonify({
            'success': True,
            'report_path': report_path,
            'content': content
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# Manual Review Queue API
# ============================================

@app.route('/api/review/pending')
def api_review_pending():
    """Get pending files for manual review."""
    from src.error_handlers import get_review_queue

    try:
        queue = get_review_queue()
        pending = queue.get_pending()

        return jsonify({
            'success': True,
            'pending': [
                {
                    'file_path': f.file_path,
                    'error_type': f.error_type.value,
                    'error_message': f.error_message,
                    'timestamp': f.timestamp.isoformat(),
                    'retry_count': f.retry_count
                }
                for f in pending
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/review/stats')
def api_review_stats():
    """Get manual review queue statistics."""
    from src.error_handlers import get_review_queue

    try:
        queue = get_review_queue()
        stats = queue.get_statistics()

        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/review/resolve', methods=['POST'])
def api_review_resolve():
    """Mark a file as resolved."""
    from src.error_handlers import get_review_queue

    try:
        data = request.get_json()
        file_path = data.get('file_path')
        notes = data.get('notes', '')

        if not file_path:
            return jsonify({'success': False, 'error': 'file_path required'}), 400

        queue = get_review_queue()
        queue.mark_resolved(file_path, notes)

        return jsonify({
            'success': True,
            'message': f'Marked {Path(file_path).name} as resolved'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# Error Handlers
# ============================================

@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', error='Page not found'), 404


@app.errorhandler(500)
def server_error(error):
    return render_template('error.html', error='Server error'), 500


# ============================================
# Context Processors
# ============================================

@app.context_processor
def inject_now():
    """Inject current datetime into all templates."""
    return {'now': datetime.now()}


if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    templates_dir = Path(__file__).parent / 'templates'
    templates_dir.mkdir(exist_ok=True)

    # Run development server
    app.run(host='127.0.0.1', port=5000, debug=True)
