"""
OCR engine module using PaddleOCR.

Handles text recognition from images and PDF files.
"""

import io
import os
from PIL import Image
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import numpy as np

from paddleocr import PaddleOCR
from loguru import logger

from .config import get_config

# Disable oneDNN to avoid compatibility issues on Windows
os.environ['FLAGS_use_mkldnn'] = '0'
os.environ['OPENBLAS_NUM_THREADS'] = '1'

# Try to import PDF processing library
try:
    import fitz  # PyMuPDF
    HAS_PDF = True
    PDF_LIBRARY = "fitz"
except ImportError:
    try:
        import pypdfium2  # Installed with PaddleOCR
        HAS_PDF = True
        PDF_LIBRARY = "pypdfium2"
    except ImportError:
        HAS_PDF = False
        PDF_LIBRARY = None
        logger.warning("No PDF processing library found. PDF support disabled.")


@dataclass
class OCRResult:
    """Result of OCR recognition"""
    text: str                    # Full text content
    lines: List[str]             # Text by line
    confidence: float            # Average confidence score (0-1)
    raw_data: Optional[dict] = field(default=None, repr=False)  # Raw OCR data

    def __str__(self) -> str:
        preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return f"OCRResult(confidence={self.confidence:.2f}, text={preview})"


class OCREngine:
    """
    OCR engine wrapper for PaddleOCR.

    Supports image formats (JPG, PNG) and PDF files.
    """

    def __init__(self, use_gpu: Optional[bool] = None):
        """
        Initialize OCR engine.

        Args:
            use_gpu: Whether to use GPU acceleration (default from config)
        """
        self.config = get_config()

        if use_gpu is None:
            use_gpu = self.config.ocr.use_gpu

        # Simplified config - only use supported parameters
        self.use_angle_cls = self.config.ocr.use_angle_cls
        self.lang = self.config.ocr.lang

        self._ocr: Optional[PaddleOCR] = None
        logger.info(f"OCR Engine initialized (GPU={use_gpu})")

    @property
    def ocr(self) -> PaddleOCR:
        """Get or create PaddleOCR instance (lazy initialization)."""
        if self._ocr is None:
            logger.debug("Initializing PaddleOCR...")
            try:
                # Basic config - only use supported parameters
                self._ocr = PaddleOCR(
                    use_angle_cls=self.use_angle_cls,
                    lang=self.lang,
                )
                logger.info("PaddleOCR initialized")
            except Exception as e:
                logger.warning(f"Standard PaddleOCR init failed: {e}")
                # Try minimal config
                try:
                    self._ocr = PaddleOCR(
                        use_angle_cls=False,
                        lang='ch',
                    )
                    logger.info("PaddleOCR initialized with minimal config")
                except Exception as e2:
                    logger.error(f"PaddleOCR initialization failed: {e2}")
                    raise
        return self._ocr

    def recognize(self, file_path: str) -> OCRResult:
        """
        Recognize text from an image file.

        Args:
            file_path: Path to image file (JPG, PNG, etc.)

        Returns:
            OCRResult: Recognition result
        """
        logger.debug(f"Recognizing image: {file_path}")

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            # Run OCR
            result = self.ocr.ocr(str(path))

            # Process result
            return self._process_ocr_result(result)

        except Exception as e:
            logger.error(f"OCR failed for {file_path}: {e}")
            return OCRResult(text="", lines=[], confidence=0.0)

    def recognize_pdf(self, pdf_path: str) -> OCRResult:
        """
        Recognize text from a PDF file.

        First tries direct text extraction (for digital PDFs).
        Falls back to OCR if no text is found (for scanned PDFs).

        Args:
            pdf_path: Path to PDF file

        Returns:
            OCRResult: Recognition result
        """
        logger.debug(f"Recognizing PDF: {pdf_path}")

        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {pdf_path}")

        try:
            import fitz  # PyMuPDF

            pdf_document = fitz.open(str(path))

            # First try direct text extraction (fast and accurate for digital PDFs)
            all_text = []
            all_lines = []

            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                text = page.get_text()

                if text.strip():
                    # Split into lines and clean up
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    all_lines.extend(lines)
                    all_text.append(text)

            pdf_document.close()

            # If we found text, return it (digital PDF)
            combined_text = '\n'.join(all_text)
            if len(combined_text.strip()) > 50:  # Threshold for "enough text"
                logger.info(f"Extracted {len(combined_text)} chars from digital PDF")
                return OCRResult(
                    text=combined_text,
                    lines=all_lines,
                    confidence=1.0,  # Digital text is 100% accurate
                    raw_data={"method": "direct_extraction"}
                )

            # No text found - this is a scanned PDF, need OCR
            logger.info("No embedded text found, using OCR...")
            return self._ocr_pdf_scanned(pdf_path)

        except ImportError:
            logger.error("PyMuPDF not available")
            return OCRResult(text="", lines=[], confidence=0.0)
        except Exception as e:
            logger.error(f"PDF text extraction failed: {e}")
            # Try OCR as fallback
            return self._ocr_pdf_scanned(pdf_path)

    def _ocr_pdf_scanned(self, pdf_path: str) -> OCRResult:
        """
        OCR scanned PDF (no embedded text).

        Converts PDF pages to images and runs OCR.

        Args:
            pdf_path: Path to PDF file

        Returns:
            OCRResult: Recognition result
        """
        logger.debug(f"Running OCR on scanned PDF: {pdf_path}")

        path = Path(pdf_path)
        try:
            import fitz

            pdf_document = fitz.open(str(path))
            all_results = []

            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]

                # Convert page to image
                mat = fitz.Matrix(2, 2)  # 2x zoom for better OCR
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))
                img_array = np.array(img)

                # Run OCR
                result = self.ocr.ocr(img_array)
                all_results.extend(result or [])

            pdf_document.close()
            return self._process_ocr_result(all_results)

        except Exception as e:
            logger.error(f"Scanned PDF OCR failed: {e}")
            return OCRResult(text="", lines=[], confidence=0.0)

    def recognize_bytes(self, image_bytes: bytes) -> OCRResult:
        """
        Recognize text from image bytes.

        Args:
            image_bytes: Image data as bytes

        Returns:
            OCRResult: Recognition result
        """
        logger.debug("Recognizing image from bytes")

        try:
            img = Image.open(io.BytesIO(image_bytes))
            img_array = np.array(img)

            result = self.ocr.ocr(img_array)
            return self._process_ocr_result(result)

        except Exception as e:
            logger.error(f"OCR from bytes failed: {e}")
            return OCRResult(text="", lines=[], confidence=0.0)

    def _process_ocr_result(self, raw_result: Optional[list]) -> OCRResult:
        """
        Process raw PaddleOCR result into OCRResult.

        Args:
            raw_result: Raw result from PaddleOCR

        Returns:
            OCRResult: Processed result
        """
        if not raw_result:
            return OCRResult(text="", lines=[], confidence=0.0)

        lines = []
        confidences = []
        full_text_parts = []

        # PaddleOCR returns:
        # [
        #   [  # Page
        #     [text_box, (text, confidence)],
        #     ...
        #   ]
        # ]

        for page in raw_result:
            if not page:
                continue

            for item in page:
                if not item or len(item) < 2:
                    continue

                # item[0] is text box (coordinates), item[1] is (text, confidence)
                text_info = item[1]
                if not text_info or len(text_info) < 2:
                    continue

                text = text_info[0]
                confidence = text_info[1]

                lines.append(text)
                confidences.append(confidence)
                full_text_parts.append(text)

        full_text = "\n".join(full_text_parts)

        # Calculate average confidence
        avg_confidence = (
            sum(confidences) / len(confidences)
            if confidences else 0.0
        )

        return OCRResult(
            text=full_text,
            lines=lines,
            confidence=avg_confidence,
            raw_data={"raw": raw_result}
        )

    def is_supported_format(self, file_path: str) -> bool:
        """
        Check if file format is supported.

        Args:
            file_path: Path to file

        Returns:
            bool: True if format is supported
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        # Image formats
        image_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'}

        # PDF
        pdf_exts = {'.pdf'}

        return ext in image_exts or ext in pdf_exts

    def recognize_auto(self, file_path: str) -> OCRResult:
        """
        Automatically choose recognition method based on file format.

        Args:
            file_path: Path to file

        Returns:
            OCRResult: Recognition result
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext == '.pdf':
            return self.recognize_pdf(file_path)
        else:
            return self.recognize(file_path)


# Global OCR engine instance
_ocr_engine: Optional[OCREngine] = None


def get_ocr_engine(reload: bool = False) -> OCREngine:
    """
    Get global OCR engine instance.

    Args:
        reload: Force reinitialize engine

    Returns:
        OCREngine: OCR engine instance
    """
    global _ocr_engine
    if _ocr_engine is None or reload:
        _ocr_engine = OCREngine()
    return _ocr_engine
