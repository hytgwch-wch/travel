"""
Baidu Pan synchronization module using bypy.

Handles downloading files from Baidu Pan to local temporary directory.
"""

import subprocess
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Set
from datetime import datetime

from loguru import logger
from .config import get_config


@dataclass
class FileMeta:
    """File metadata from Baidu Pan"""
    path: str           # Remote path (relative to /apps/bypy/)
    size: int           # File size in bytes
    mtime: int          # Modification time (Unix timestamp)
    md5: Optional[str]  # MD5 hash (if available)
    is_dir: bool = False

    def __str__(self) -> str:
        return f"FileMeta(path={self.path}, size={self.size}, mtime={self.mtime})"


class BypySyncManager:
    """
    Baidu Pan synchronization manager using bypy command-line tool.
    """

    def __init__(self):
        """Initialize sync manager."""
        self.config = get_config()
        self.temp_dir = Path(self.config.baidu_pan.temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._verify_bypy()

    def _verify_bypy(self):
        """Verify bypy is installed and authorized."""
        try:
            result = subprocess.run(
                ["python", "-m", "bypy", "quota"],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            # Check if authorization failed
            if "Traceback" in result.stderr or "EOFError" in result.stderr:
                logger.warning("Bypy may not be properly authorized")
            else:
                logger.debug("Bypy verified")
        except Exception as e:
            logger.error(f"Bypy verification failed: {e}")
            raise RuntimeError("Bypy not available or not authorized")

    def _run_bypy(self, args: List[str], timeout: int = 120) -> tuple[bool, str, str]:
        """
        Run bypy command with specified arguments.

        Args:
            args: Command arguments (excluding 'bypy')
            timeout: Command timeout in seconds

        Returns:
            Tuple of (success, stdout, stderr)
        """
        cmd = ["python", "-m", "bypy"] + args

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='gbk',  # Use GBK for Windows compatibility
                errors='replace'
            )

            success = result.returncode == 0
            return success, result.stdout, result.stderr

        except subprocess.TimeoutExpired:
            logger.error(f"Bypy command timed out: {' '.join(args)}")
            return False, "", "Command timed out"
        except Exception as e:
            logger.error(f"Bypy command failed: {e}")
            return False, "", str(e)

    def list_remote_files(self, remote_dir: Optional[str] = None) -> List[FileMeta]:
        """
        List files in remote Baidu Pan directory.

        Args:
            remote_dir: Remote directory path (default from config)

        Returns:
            List[FileMeta]: List of file metadata
        """
        if remote_dir is None:
            remote_dir = self.config.baidu_pan.remote_dir

        logger.info(f"Listing remote files: {remote_dir}")

        success, stdout, stderr = self._run_bypy(["list", remote_dir], timeout=60)

        if not success:
            logger.error(f"Failed to list remote files: {stderr}")
            return []

        files = []
        for line in stdout.split('\n'):
            line = line.strip()
            if not line:
                continue

            # Parse bypy list output format:
            # D/F <name> <size> <date> <time> <md5>
            parts = line.split()
            if len(parts) < 5:
                continue

            try:
                is_dir = parts[0] == 'D'
                name = parts[1]
                size = int(parts[2]) if not is_dir else 0

                # Parse date/time (format: YYYY-MM-DD, HH:MM:SS)
                date_str = f"{parts[3]} {parts[4]}"
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                    mtime = int(dt.timestamp())
                except:
                    mtime = 0

                md5 = parts[5] if len(parts) > 5 else None

                # Skip directories
                if is_dir:
                    continue

                # Construct full path (bypy uses paths relative to /apps/bypy/)
                # Don't add directory prefix if it's already included
                if remote_dir and remote_dir != ".":
                    # For bypy, paths are like "invoices/filename.pdf"
                    full_path = f"{remote_dir}/{name}"
                else:
                    full_path = name

                files.append(FileMeta(
                    path=full_path,
                    size=size,
                    mtime=mtime,
                    md5=md5,
                    is_dir=is_dir
                ))

            except (ValueError, IndexError) as e:
                logger.debug(f"Failed to parse line: {line}")
                continue

        logger.info(f"Found {len(files)} remote files")
        return files

    def download_file(self, remote_path: str, local_path: Optional[Path] = None) -> bool:
        """
        Download a single file from Baidu Pan.

        Args:
            remote_path: Remote file path
            local_path: Local save path (default: temp_dir/basename)

        Returns:
            bool: True if download successful
        """
        if local_path is None:
            local_path = self.temp_dir / Path(remote_path).name

        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Downloading: {remote_path} -> {local_path}")

        # bypy download command: bypy download <remote> <local>
        success, stdout, stderr = self._run_bypy(
            ["download", remote_path, str(local_path)],
            timeout=300  # 5 minutes timeout for download
        )

        if success:
            # Verify file exists
            if local_path.exists():
                size = local_path.stat().st_size
                logger.info(f"Downloaded: {remote_path} ({size} bytes)")
                return True
            else:
                logger.error(f"Download reported success but file not found: {local_path}")
                return False
        else:
            logger.error(f"Download failed: {remote_path} - {stderr}")
            return False

    def sync_new_files(self, known_files: Set[str]) -> List[str]:
        """
        Sync new files from Baidu Pan.

        Args:
            known_files: Set of already processed remote paths

        Returns:
            List[str]: List of downloaded local file paths
        """
        logger.info("Checking for new files...")

        # Download entire directory (more reliable than individual files)
        remote_dir = self.config.baidu_pan.remote_dir

        logger.info(f"Downloading directory: {remote_dir}")
        success, stdout, stderr = self._run_bypy(
            ["download", remote_dir, str(self.temp_dir)],
            timeout=600  # 10 minutes for directory download
        )

        if not success:
            logger.error(f"Failed to download directory: {stderr}")
            return []

        # Get all downloaded files
        downloaded = []
        if self.temp_dir.exists():
            for file_path in self.temp_dir.iterdir():
                if file_path.is_file():
                    # Check if this is a new file
                    if file_path.name not in known_files:
                        downloaded.append(str(file_path))
                        logger.info(f"New file: {file_path.name}")
                    else:
                        logger.debug(f"Already processed: {file_path.name}")

        logger.info(f"Downloaded {len(downloaded)} new files")
        return downloaded

    def upload_file(self, local_path: str, remote_dir: Optional[str] = None) -> bool:
        """
        Upload a file to Baidu Pan.

        Args:
            local_path: Local file path to upload
            remote_dir: Remote directory (default from config)

        Returns:
            bool: True if upload successful
        """
        if remote_dir is None:
            remote_dir = self.config.baidu_pan.remote_dir

        logger.info(f"Uploading: {local_path} -> {remote_dir}")

        # bypy upload command: bypy upload <local> <remote>
        success, stdout, stderr = self._run_bypy(
            ["upload", local_path, remote_dir],
            timeout=300
        )

        if success:
            logger.info(f"Uploaded: {local_path}")
            return True
        else:
            logger.error(f"Upload failed: {local_path} - {stderr}")
            return False

    def delete_remote_file(self, remote_path: str) -> bool:
        """
        Delete a file from Baidu Pan.

        Args:
            remote_path: Remote file path to delete

        Returns:
            bool: True if deletion successful
        """
        logger.info(f"Deleting remote file: {remote_path}")

        # bypy delete command: bypy delete <remote>
        success, stdout, stderr = self._run_bypy(
            ["delete", remote_path],
            timeout=60
        )

        if success:
            logger.info(f"Deleted: {remote_path}")
            return True
        else:
            logger.error(f"Delete failed: {remote_path} - {stderr}")
            return False

    def create_remote_dir(self, remote_dir: str) -> bool:
        """
        Create a directory in Baidu Pan.

        Args:
            remote_dir: Remote directory path to create

        Returns:
            bool: True if creation successful
        """
        logger.info(f"Creating remote directory: {remote_dir}")

        # bypy mkdir command: bypy mkdir <remote>
        success, stdout, stderr = self._run_bypy(
            ["mkdir", remote_dir],
            timeout=60
        )

        if success:
            logger.info(f"Created directory: {remote_dir}")
            return True
        else:
            # Directory might already exist
            if "already exists" in stderr.lower() or "已存在" in stderr:
                logger.debug(f"Directory already exists: {remote_dir}")
                return True
            logger.error(f"Failed to create directory: {remote_dir} - {stderr}")
            return False
