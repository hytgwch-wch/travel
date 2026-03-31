# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated business travel invoice processing system. Syncs invoices from email (IMAP), uses PaddleOCR for recognition, parses invoice info, renames files, and organizes into categorized directories. Also groups invoices into complete business trips.

**Primary data source**: Email (IMAP) - downloads attachments from travel-related emails
**Secondary**: Baidu Pan (deprecated but still available)

## Common Commands

### Run the invoice processor
```bash
# Run once
python main.py --run

# Daily scheduled task
python main.py --daily

# Dry run (no actual file changes)
python main.py --run --dry-run

# Show statistics
python main.py --stats

# Show recent records
python main.py --recent

# Show failed records
python main.py --failed

# Group invoices into business trips
python main.py --trips
python main.py --trips --report-only  # Generate report only
```

### Manual testing commands
```bash
# Test email connection
python test_email_manual.py --connect

# List recent emails
python test_email_manual.py --list

# Full workflow test
python test_workflow.py

# Test invoice matching
python -c "from src.invoice_matcher import match_invoices; match_invoices()"
```

### Development
```bash
# Format code
black src/ tests/

# Run tests (TODO - Phase 5)
pytest tests/
```

## Architecture

### Data Flow
```
Email (IMAP) → email_sync.py download → temp/ → archive extraction
    → ocr_engine.py (PaddleOCR) → parser.py → InvoiceInfo
    → renamer.py → organizer.py → invoices/{YYYY}/{MM}/{category}/
    → invoice_matcher.py (match taxi invoices with trip receipts)
    → trip_grouper.py (optional) → trips/{traveler}/{start}_{end}_{cities}/
```

### Key Modules

**email_sync.py**: IMAP email sync manager (primary). Downloads attachments, extracts archives (.zip), tracks email UIDs. Key filter: sender domains (@ctrip.com, @ceair.com, @marriott.com, @didiglobal.com, etc.) and subject keywords.

**invoice_matcher.py**: Matches taxi invoices with trip receipts by amount. Trip receipts (行程单) contain trip date ranges; invoices (发票) use billing dates. This module renames invoices to use trip date ranges instead of billing dates.

**ocr_engine.py**: PaddleOCR wrapper. Methods: `recognize()`, `recognize_pdf()`, `recognize_auto()`.

**parser.py**: Extracts InvoiceInfo from OCR text using regex patterns from `config/parsers.yaml`. Core types: InvoiceType enum, InvoiceInfo dataclass.

**scheduler.py**: TaskScheduler orchestrates the full pipeline. Processes files grouped by email for cross-referencing (e.g., trip receipts inform invoice types/dates). Uses SQLite (`data/records.db`) for deduplication.

**trip_grouper.py**: Groups invoices into complete business trips. Detects departure from home (杭州) → destination → return. Matches transfer invoices with flight dates.

### Important Constants

- Home city for trip detection: `TripGrouper.HOME_CITY = "杭州"`
- Email IMAP tracking: Uses UID to avoid re-downloading same emails
- Taxi invoice naming: Uses date range format `start至end` (e.g., `2026-01-28至2026-02-27`)

### Processing Order Within Email

Files from the same email are processed in this order:
1. **Bills** (结账单) - Extract check-in/check-out dates for hotel invoices
2. **Trip receipts** (行程单) - Determine type and trip date ranges for matching invoices
3. **Invoices** (发票) - Use info from bills/trip receipts when available

### Database Schema

`data/records.db` contains `processed_files` table:
- `remote_path` (UNIQUE) - identifies file (or email UID for email sync)
- `local_path`, `final_path` - file locations
- `invoice_type`, `invoice_date`, `amount`, `traveler` - extracted info
- `source_type`, `email_uid`, `email_subject` - email metadata
- `raw_ocr_text` - First 1000 chars of OCR text for debugging
- `status` - success/failed

### Archive Handling

Email attachments in .zip/.rar/.7z format are:
1. Downloaded to temp/
2. Extracted automatically (PDF/images only)
3. Archive deleted after extraction
4. Extracted files processed normally

## Invoice Types and Naming

| Type | Suffix | Date Format | Example |
|-----|--------|-------------|---------|
| Airplane | _行程单 or (none) | Single date | `2026-03-23_机票_杭州_大连_620.00_王春晖.pdf` |
| Airport Transfer | _行程单 | Single date | `2026-03-23_接送机_杭州市区_杭州萧山机场_133.00_王春晖_行程单.pdf` |
| Train | (none) | Single date | `2026-03-28_火车_丽水_杭州南_72.00_王春晖.pdf` |
| Taxi (receipt) | _行程单 | Date range | `2026-01-28至2026-02-27_打车_36.00_王春晖_行程单.pdf` |
| Taxi (invoice) | _发票 | Date range | `2026-01-28至2026-02-27_打车_36.00_王春晖_发票.pdf` |
| Hotel | (none) | Check-in date | `2026-03-11_住宿_上海_2026.03.11-2026.03.12_374.00_王春晖.pdf` |

**Key distinction**: `行程单` = trip receipt (service summary), `发票` = official invoice (billing). For taxi/airport transfers, invoices are renamed to match trip receipt date ranges.

## Configuration Files

- `config/config.yaml` - Email IMAP settings, paths, default traveler, processing options
- `config/parsers.yaml` - Invoice type detection rules, field extraction regex patterns (includes formal Chinese numerals: 壹贰叁肆伍陆柒捌玖拾佰仟万)
- `config/travelers.yaml` - Traveler names and aliases

## Adding New Invoice Types

Update these files:
1. `src/parser.py` - Add to `InvoiceType` enum
2. `config/parsers.yaml` - Add detection keywords and extraction patterns
3. `src/renamer.py` - Add naming template
4. `src/organizer.py` - Add directory mapping (交通/住宿/餐饮/其他)

## Debugging OCR Issues

When OCR extraction fails (wrong amount, date, etc.):
1. Check `raw_ocr_text` in database for actual OCR output
2. Test regex patterns in `config/parsers.yaml`
3. Chinese financial documents use formal numerals (壹贰叁肆伍陆柒捌玖拾佰仟万)
4. Amount extraction priority: formal numerals + ¥ symbol > (小写) >价税合计 > generic ¥

## Common Issues

**Taxi invoices have billing date instead of trip date**: Run `invoice_matcher.py` to match with trip receipts by amount.

**Multiple receipts/invoices with same amount**: Matcher tracks which are matched to avoid duplication.

**Encoding issues with Chinese filenames**: Avoid direct string checks like `'王春晖' in filename` - use regex patterns instead.

**Email UID tracking**: Each email has a unique UID; stored in database to prevent re-downloading.
