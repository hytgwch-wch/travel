"""
Email synchronization module using IMAP.

Handles downloading invoice attachments from email to local temporary directory.
Replaces BypySyncManager for email-based invoice collection.
"""

import imaplib
import email
import re
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple
from datetime import datetime, timedelta

from loguru import logger

try:
    from .config import get_config
except ImportError:
    from src.config import get_config


@dataclass
class EmailMeta:
    """Email metadata from IMAP server"""
    uid: str                    # IMAP UID (unique identifier)
    subject: str                # Email subject
    sender: str                 # Sender email address
    sender_name: str            # Sender display name
    date: datetime              # Email date
    has_attachment: bool        # Whether email has attachments
    message_id: str = ""        # Message-ID header

    def __str__(self) -> str:
        return f"EmailMeta(uid={self.uid}, subject={self.subject}, sender={self.sender})"


@dataclass
class AttachmentMeta:
    """Attachment metadata from email"""
    filename: str               # Attachment filename
    content_type: str           # MIME type (e.g., 'application/pdf')
    size: int                   # Size in bytes
    content_id: str = ""        # Content-ID (for inline attachments)

    def is_invoice(self) -> bool:
        """Check if attachment is likely an invoice."""
        invoice_extensions = {'.pdf', '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.zip', '.rar', '.7z'}
        invoice_content_types = {
            'application/pdf',
            'image/jpeg',
            'image/png',
            'image/bmp',
            'image/tiff',
            'application/zip',
            'application/x-zip-compressed',
            'application/x-rar-compressed',
            'application/x-7z-compressed'
        }

        # Check extension
        ext = Path(self.filename).suffix.lower()
        if ext in invoice_extensions:
            return True

        # Check content type
        if self.content_type in invoice_content_types:
            return True

        return False


class EmailFilter:
    """
    Email filter for travel-related invoices.

    Implements multi-layer filtering:
    1. Sender domain/email matching
    2. Subject keyword matching
    3. Attachment type checking
    """

    def __init__(self, config):
        """
        Initialize email filter.

        Args:
            config: EmailConfig instance
        """
        self.config = config
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile filter patterns from config."""
        # Sender patterns - convert to lowercase for matching
        self.sender_domains = set()
        for pattern in self.config.sender_keywords:
            pattern_lower = pattern.lower()
            if pattern_lower.startswith('@'):
                self.sender_domains.add(pattern_lower[1:])
            else:
                self.sender_domains.add(pattern_lower)

        # Subject keywords
        self.subject_keywords = set(kw.lower() for kw in self.config.subject_keywords)

        # Invoice file extensions
        self.invoice_extensions = set(
            ext.lower() for ext in self.config.attachment_extensions
        )

    def is_sender_match(self, sender_email: str, sender_name: str = "") -> bool:
        """
        Check if sender matches travel-related domains.

        Args:
            sender_email: Sender email address
            sender_name: Sender display name

        Returns:
            bool: True if matches
        """
        # Extract domain from email
        if '@' in sender_email:
            domain = sender_email.split('@')[1].lower()
            if domain in self.sender_domains:
                return True

        # Check full email match
        sender_lower = sender_email.lower()
        for pattern in self.sender_domains:
            if pattern in sender_lower:
                return True

        # Check sender name for keywords
        if sender_name:
            name_lower = sender_name.lower()
            for keyword in self.subject_keywords:
                if keyword in name_lower:
                    return True

        return False

    def is_subject_match(self, subject: str) -> bool:
        """
        Check if subject contains travel-related keywords.

        Args:
            subject: Email subject

        Returns:
            bool: True if matches
        """
        if not subject:
            return False

        subject_lower = subject.lower()
        for keyword in self.subject_keywords:
            if keyword in subject_lower:
                return True
        return False

    def is_valid_attachment(self, filename: str) -> bool:
        """
        Check if attachment is likely an invoice.

        Args:
            filename: Attachment filename

        Returns:
            bool: True if valid
        """
        ext = Path(filename).suffix.lower()
        return ext in self.invoice_extensions

    def should_process_email(self, email_meta: EmailMeta) -> bool:
        """
        Decide if email should be processed.

        Args:
            email_meta: Email metadata

        Returns:
            bool: True if should process
        """
        # Must have attachment
        if not email_meta.has_attachment:
            return False

        # Check sender OR subject (at least one must match)
        sender_match = self.is_sender_match(email_meta.sender, email_meta.sender_name)
        subject_match = self.is_subject_match(email_meta.subject)

        return sender_match or subject_match


class EmailSyncManager:
    """
    Email synchronization manager using IMAP protocol.

    Replaces BypySyncManager to download invoice attachments from email.
    Maintains compatible interface: sync_new_files(known_files) -> List[str]
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize email sync manager.

        Args:
            config_path: Optional path to configuration file
        """
        self.config = get_config()
        self.email_config = self.config.email
        self.temp_dir = Path(self.config.email.temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # IMAP connection
        self._imap: Optional[imaplib.IMAP4_SSL] = None
        self._connected = False

        # Email filter
        self.filter = EmailFilter(self.email_config)

        # Track downloaded files with their email metadata
        self.downloaded_files_meta: Dict[str, EmailMeta] = {}

        logger.info("EmailSyncManager initialized")

    def connect(self) -> bool:
        """
        Connect to IMAP server and authenticate.

        Returns:
            bool: True if connection successful
        """
        try:
            logger.info(f"Connecting to {self.email_config.imap_server}:{self.email_config.imap_port}")

            # Connect to IMAP server
            self._imap = imaplib.IMAP4_SSL(
                self.email_config.imap_server,
                self.email_config.imap_port
            )

            # Login
            self._imap.login(
                self.email_config.email_address,
                self.email_config.authorization_code
            )

            # Select mailbox
            self._imap.select(self.email_config.mailbox)

            self._connected = True
            logger.info(f"Connected to {self.email_config.imap_server} as {self.email_config.email_address}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to email server: {e}")
            self._connected = False
            return False

    def disconnect(self):
        """Close IMAP connection."""
        if self._imap and self._connected:
            try:
                self._imap.close()
                self._imap.logout()
                logger.info("Disconnected from email server")
            except Exception as e:
                logger.warning(f"Error during disconnect: {e}")
            finally:
                self._connected = False

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()

    def _ensure_connection(self):
        """Ensure IMAP connection is active."""
        if not self._connected or self._imap is None:
            if not self.connect():
                raise RuntimeError("Failed to establish IMAP connection")

    def list_emails(self,
                    since_date: Optional[datetime] = None,
                    limit: int = 100) -> List[EmailMeta]:
        """
        List emails from mailbox.

        Args:
            since_date: Only list emails after this date (None = all)
            limit: Maximum number of emails to retrieve

        Returns:
            List[EmailMeta]: List of email metadata
        """
        self._ensure_connection()

        try:
            # Build search criteria
            criteria_parts = []

            # Search for emails with attachments (simplified - check all)
            # We'll filter for attachments when fetching

            if since_date:
                date_str = since_date.strftime('%d-%b-%Y')
                criteria_parts.append(f'(SINCE {date_str})')

            search_cmd = ' '.join(criteria_parts) if criteria_parts else 'ALL'

            logger.debug(f"IMAP search criteria: {search_cmd}")

            # Search for matching emails
            status, messages = self._imap.search(None, search_cmd)

            if status != 'OK':
                logger.error(f"IMAP search failed: {status}")
                return []

            # Get email IDs
            email_ids = messages[0].split()

            # Limit results - get most recent
            if limit and len(email_ids) > limit:
                email_ids = email_ids[-limit:]

            logger.info(f"Found {len(email_ids)} emails matching criteria")

            # Fetch email metadata
            emails = []
            for email_id in email_ids:
                try:
                    email_meta = self._fetch_email_meta(email_id)
                    if email_meta:
                        emails.append(email_meta)
                except Exception as e:
                    logger.debug(f"Failed to fetch email {email_id}: {e}")
                    continue

            return emails

        except Exception as e:
            logger.error(f"Failed to list emails: {e}")
            return []

    def _fetch_email_meta(self, email_id: bytes) -> Optional[EmailMeta]:
        """
        Fetch metadata for a single email.

        Args:
            email_id: Email UID as bytes

        Returns:
            EmailMeta if successful, None otherwise
        """
        try:
            # Fetch email headers only first
            status, msg_data = self._imap.fetch(
                email_id,
                '(BODY.PEEK[HEADER])'
            )

            if status != 'OK' or not msg_data or not msg_data[0]:
                return None

            # Parse email headers
            response = msg_data[0]
            if isinstance(response, tuple):
                raw_email = response[1]
            else:
                raw_email = response

            msg = email.message_from_bytes(raw_email)

            # Extract metadata
            subject = self._decode_header(msg.get('Subject', ''))
            sender = msg.get('From', '')
            sender_name, sender_email = self._parse_sender(sender)
            date_str = msg.get('Date', '')
            message_id = msg.get('Message-ID', '')

            # Parse date
            try:
                email_date = parsedate_to_datetime(date_str)
            except:
                email_date = datetime.now()

            # Fetch BODYSTRUCTURE to check for attachments
            status2, struct_data = self._imap.fetch(email_id, '(BODYSTRUCTURE)')
            has_attachment = False
            if status2 == 'OK' and struct_data and struct_data[0]:
                struct_str = str(struct_data[0])
                # Check for attachment indicators
                # BODYSTRUCTURE format: ("content_type" ("name" "filename") or ("attachment" ...)
                has_attachment = (
                    '("attachment"' in struct_str or  # Explicit attachment disposition
                    'APPLICATION/PDF' in struct_str.upper() or
                    '("image"' in struct_str.lower() or  # Image content type
                    'IMAGE/' in struct_str.upper() or
                    '("name"' in struct_str.lower()  # Has filename parameter
                )

            return EmailMeta(
                uid=email_id.decode(),
                subject=subject,
                sender=sender_email,
                sender_name=sender_name,
                date=email_date,
                has_attachment=has_attachment,
                message_id=message_id
            )

        except Exception as e:
            logger.debug(f"Failed to parse email {email_id}: {e}")
            return None

    def _has_attachment_from_response(self, msg_data) -> bool:
        """Check if email has attachment from IMAP response."""
        # This method is no longer used, kept for compatibility
        return False

    def _has_attachment(self, msg) -> bool:
        """Check if email has attachments."""
        for part in msg.walk():
            if part.get_content_maintype() != 'multipart' and part.get('Content-Disposition'):
                return True
        return False

    def _decode_header(self, header: str) -> str:
        """
        Decode email header (handles encoding).

        Args:
            header: Raw header string

        Returns:
            str: Decoded header string
        """
        if not header:
            return ""

        decoded_parts = decode_header(header)
        decoded_str = ''

        for content, encoding in decoded_parts:
            if isinstance(content, bytes):
                if encoding:
                    try:
                        decoded_str += content.decode(encoding)
                    except:
                        decoded_str += content.decode('utf-8', errors='ignore')
                else:
                    decoded_str += content.decode('utf-8', errors='ignore')
            else:
                decoded_str += str(content)

        return decoded_str

    def _parse_sender(self, sender: str) -> Tuple[str, str]:
        """
        Parse sender field to extract name and email.

        Args:
            sender: Raw sender string (e.g., 'John Doe <john@example.com>')

        Returns:
            Tuple[str, str]: (sender_name, sender_email)
        """
        addr = parseaddr(sender)
        return addr[0], addr[1]

    def _download_attachments(self, email_id: bytes) -> List[Tuple[str, Path, EmailMeta]]:
        """
        Download all invoice attachments from an email.

        Args:
            email_id: Email UID

        Returns:
            List[Tuple[str, Path, EmailMeta]]: List of (filename, local_path, email_meta)
        """
        try:
            # Fetch complete email
            status, msg_data = self._imap.fetch(email_id, '(RFC822)')

            if status != 'OK':
                return []

            # Parse email
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            # Get email metadata for tracking
            subject = self._decode_header(msg.get('Subject', ''))
            sender = msg.get('From', '')
            sender_name, sender_email = self._parse_sender(sender)
            date_str = msg.get('Date', '')
            try:
                email_date = parsedate_to_datetime(date_str)
            except:
                email_date = datetime.now()

            email_meta = EmailMeta(
                uid=email_id.decode(),
                subject=subject,
                sender=sender_email,
                sender_name=sender_name,
                date=email_date,
                has_attachment=True
            )

            downloaded = []

            # Walk through email parts
            for part in msg.walk():
                # Skip multipart containers
                if part.get_content_maintype() == 'multipart':
                    continue

                # Get filename
                filename = part.get_filename()
                if not filename:
                    continue

                # Decode filename
                filename = self._decode_header(filename)

                # Check if file is invoice-like
                attachment_meta = AttachmentMeta(
                    filename=filename,
                    content_type=part.get_content_type(),
                    size=len(part.get_payload(decode=True)) if part.get_payload(decode=True) else 0
                )

                if not attachment_meta.is_invoice():
                    logger.debug(f"Skipping non-invoice attachment: {filename}")
                    continue

                # Download attachment
                local_path = self.temp_dir / filename
                local_path = self._make_unique_filename(local_path)

                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        with open(local_path, 'wb') as f:
                            f.write(payload)

                        downloaded.append((filename, local_path, email_meta))
                        logger.info(f"Downloaded: {filename}")

                        # Extract if it's a compressed file
                        extracted_files = self._extract_archive(local_path)
                        if extracted_files or local_path.suffix.lower() in ['.zip', '.rar', '.7z']:
                            # Remove the archive file from downloaded list since it's been extracted/deleted
                            downloaded.pop()
                            if extracted_files:
                                downloaded.extend(extracted_files)
                    else:
                        logger.warning(f"Empty payload for {filename}")

                except Exception as e:
                    logger.error(f"Failed to save {filename}: {e}")

            return downloaded

        except Exception as e:
            logger.error(f"Failed to download attachments from email {email_id}: {e}")
            return []

    def _make_unique_filename(self, path: Path) -> Path:
        """
        Make filename unique by adding counter if exists.

        Args:
            path: Original path

        Returns:
            Path: Unique path
        """
        if not path.exists():
            return path

        counter = 1
        stem = path.stem
        suffix = path.suffix
        parent = path.parent

        while True:
            new_path = parent / f"{stem}_{counter}{suffix}"
            if not new_path.exists():
                return new_path
            counter += 1

    def _extract_archive(self, archive_path: Path) -> List[Tuple[str, Path, 'EmailMeta']]:
        """
        Extract compressed archive and return list of extracted files.

        Handles nested archives (e.g., zip containing zip files) by recursively extracting.

        Args:
            archive_path: Path to the archive file

        Returns:
            List of (filename, local_path, email_meta) for extracted files
        """
        import zipfile
        import py7zr
        import shutil

        archive_path_str = str(archive_path)
        archive_ext = archive_path.suffix.lower()
        extracted = []

        # Only extract specific archive types
        if archive_ext not in ['.zip', '.rar', '.7z']:
            return []

        # Create extraction directory
        extract_dir = archive_path.parent / archive_path.stem
        extract_dir.mkdir(exist_ok=True)

        logger.info(f"Extracting archive: {archive_path.name}")

        try:
            if archive_ext == '.zip':
                with zipfile.ZipFile(archive_path_str, 'r') as zf:
                    all_files = zf.namelist()

                    # First, extract all files
                    for filename in all_files:
                        # Skip directories and __MACOSX
                        if filename.endswith('/') or filename.startswith('__MACOSX') or filename.startswith('.'):
                            continue

                        # Extract the file
                        try:
                            extracted_path = extract_dir / filename
                            zf.extract(filename, path=str(extract_dir))
                            logger.debug(f"  Extracted: {filename}")
                        except Exception as e:
                            logger.warning(f"  Failed to extract {filename}: {e}")

                    # Now, check for nested archives and extract them
                    for filename in all_files:
                        if filename.endswith('/') or filename.startswith('__MACOSX') or filename.startswith('.'):
                            continue

                        extracted_file = extract_dir / filename
                        if not extracted_file.is_file():
                            continue

                        # Check if this is another archive
                        file_ext = extracted_file.suffix.lower()
                        if file_ext in ['.zip', '.rar', '.7z']:
                            logger.info(f"  Found nested archive: {filename}")
                            # Recursively extract
                            nested_extracted = self._extract_archive(extracted_file)
                            if nested_extracted:
                                extracted.extend(nested_extracted)
                                # Delete the nested archive after extraction
                                try:
                                    extracted_file.unlink()
                                    logger.info(f"  Deleted nested archive: {filename}")
                                except Exception as e:
                                    logger.warning(f"  Could not delete nested archive {filename}: {e}")
                        # Check if it's an invoice file
                        elif any(filename.lower().endswith(ext) for ext in ['.pdf', '.jpg', '.jpeg', '.png']):
                            # Make sure filename is unique
                            final_path = extract_dir / filename.split('/')[-1]
                            final_path = self._make_unique_filename(final_path)

                            # Move if needed
                            if final_path != extracted_file:
                                shutil.move(str(extracted_file), str(final_path))

                            extracted.append((filename, final_path, None))
                            logger.info(f"  Extracted invoice: {filename}")

            elif archive_ext == '.7z':
                with py7zr.SevenZipFile(archive_path_str, mode='r') as zf:
                    all_files = zf.getnames()

                    # First, extract all files
                    for filename in all_files:
                        # Skip directories and __MACOSX
                        if filename.endswith('/') or filename.startswith('__MACOSX') or filename.startswith('.'):
                            continue

                        # Extract the file
                        try:
                            extracted_path = extract_dir / filename.split('/')[-1]
                            zf.extract(targets=filename, path=str(extract_dir))
                            logger.debug(f"  Extracted: {filename}")
                        except Exception as e:
                            logger.warning(f"  Failed to extract {filename}: {e}")

                    # Check for nested archives and invoice files
                    for filename in all_files:
                        if filename.endswith('/') or filename.startswith('__MACOSX') or filename.startswith('.'):
                            continue

                        extracted_file = extract_dir / filename.split('/')[-1]
                        if not extracted_file.is_file():
                            continue

                        # Check if this is another archive
                        file_ext = extracted_file.suffix.lower()
                        if file_ext in ['.zip', '.rar', '.7z']:
                            logger.info(f"  Found nested archive: {filename}")
                            # Recursively extract
                            nested_extracted = self._extract_archive(extracted_file)
                            if nested_extracted:
                                extracted.extend(nested_extracted)
                                # Delete the nested archive after extraction
                                try:
                                    extracted_file.unlink()
                                    logger.info(f"  Deleted nested archive: {filename}")
                                except Exception as e:
                                    logger.warning(f"  Could not delete nested archive {filename}: {e}")
                        # Check if it's an invoice file
                        elif any(filename.lower().endswith(ext) for ext in ['.pdf', '.jpg', '.jpeg', '.png']):
                            # Make sure filename is unique
                            final_path = self._make_unique_filename(extracted_file)

                            extracted.append((filename, final_path, None))
                            logger.info(f"  Extracted invoice: {filename}")

            elif archive_ext == '.rar':
                # RAR extraction requires unrar command
                logger.warning(f"RAR extraction not supported, skipping: {archive_path.name}")
                # Optionally use rarfile or subprocess with unrar

            # Clean up empty extraction directory
            if extract_dir.exists() and not list(extract_dir.iterdir()):
                extract_dir.rmdir()

            # Delete the archive after extraction
            try:
                archive_path.unlink()
                logger.info(f"  Deleted archive: {archive_path.name}")
            except Exception as e:
                logger.warning(f"Could not delete archive {archive_path.name}: {e}")

        except Exception as e:
            logger.error(f"Failed to extract {archive_path.name}: {e}")

        return extracted

    def sync_new_files(self, known_files: Set[str], db=None) -> List[str]:
        """
        Sync new invoice attachments from email.

        This method maintains compatibility with BypySyncManager interface.
        It uses email UID as the unique identifier instead of file path.

        Args:
            known_files: Set of already processed email UIDs (for compatibility, ignored if db provided)
            db: Optional database connection to query processed email UIDs

        Returns:
            List[str]: List of downloaded local file paths
        """
        logger.info("Checking for new emails...")

        # Connect to email server
        if not self._connected:
            self.connect()

        # Get known email UIDs from database if provided
        known_uids: Set[str] = set()
        if db:
            try:
                known_uids = db.get_known_email_uids()
                logger.debug(f"Known email UIDs from database: {len(known_uids)}")
            except Exception as e:
                logger.warning(f"Failed to get known email UIDs: {e}")

        # Calculate date range
        since_date = datetime.now() - timedelta(days=self.email_config.check_days)

        # List emails
        emails = self.list_emails(
            since_date=since_date,
            limit=self.email_config.max_emails
        )

        logger.info(f"Found {len(emails)} emails in date range")

        # Filter travel-related emails
        travel_emails = [
            e for e in emails
            if self.filter.should_process_email(e)
        ]

        logger.info(f"Travel-related emails: {len(travel_emails)}")

        # Download attachments from new emails
        downloaded_files = []

        for email_meta in travel_emails:
            # Check if already processed (use known_uids if available)
            check_set = known_uids if known_uids else known_files
            if email_meta.uid in check_set:
                logger.debug(f"Already processed: {email_meta.uid}")
                continue

            # Download attachments
            try:
                attachments = self._download_attachments(
                    email_meta.uid.encode()
                )

                for orig_filename, local_path, attachment_email_meta in attachments:
                    downloaded_files.append(str(local_path))
                    # Store file path -> email metadata mapping
                    self.downloaded_files_meta[str(local_path)] = attachment_email_meta

                if attachments and self.email_config.mark_as_read:
                    # Mark email as seen
                    self._imap.store(email_meta.uid.encode(), '+FLAGS', '\\Seen')
                    logger.debug(f"Marked email {email_meta.uid} as read")

            except Exception as e:
                logger.error(f"Failed to process email {email_meta.uid}: {e}")
                continue

        # Filter out already-processed files (important for ZIP-extracted files)
        if db:
            filtered_files = []
            for file_path in downloaded_files:
                # Check if this specific file was already processed
                # For files in subdirectories, check multiple possible paths
                path_obj = Path(file_path)
                filename = path_obj.name

                # Get email metadata for this file
                email_meta = self.downloaded_files_meta.get(str(file_path))

                # Check using email_uid + filename combination (more accurate)
                is_processed = False
                if email_meta:
                    is_processed = db.is_processed_by_email(str(email_meta.uid), filename)
                else:
                    # Fallback to old method for non-email files
                    is_processed = db.is_processed(filename)

                if not is_processed:
                    filtered_files.append(file_path)
                else:
                    logger.debug(f"Skipping already processed file: {filename} (from email {email_meta.uid if email_meta else 'unknown'})")
                    # Remove the file metadata since we're not returning it
                    self.downloaded_files_meta.pop(file_path, None)
                    # Delete the file from disk as well
                    try:
                        path_obj.unlink()
                    except:
                        pass

            logger.info(f"Downloaded {len(downloaded_files)} files, {len(filtered_files)} are new")
            return filtered_files

        logger.info(f"Downloaded {len(downloaded_files)} new files")
        return downloaded_files


def test_connection() -> bool:
    """Test email connection."""
    manager = EmailSyncManager()
    try:
        result = manager.connect()
        if result:
            manager.disconnect()
        return result
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return False


if __name__ == "__main__":
    # Test connection
    print("Testing email connection...")
    if test_connection():
        print("Connection successful!")
    else:
        print("Connection failed!")
