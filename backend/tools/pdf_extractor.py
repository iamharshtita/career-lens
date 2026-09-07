"""
pdf_extractor.py — pdfplumber-based PDF text extraction utility.

Provides a single public function, `extract_pdf_text`, that accepts either
raw PDF bytes or a binary file-like object and returns the concatenated
plain-text content of all pages.  A typed `PDFExtractionError` is raised for
any condition that makes extraction impossible: corrupt data, password
protection, or a document that contains no extractable text.
"""

from __future__ import annotations

import io
from typing import BinaryIO, Union

import pdfplumber


class PDFExtractionError(Exception):
    """Raised when a PDF cannot be read or yields no text.

    Attributes:
        reason: A human-readable description of the failure.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def extract_pdf_text(source: Union[bytes, BinaryIO]) -> str:
    """Extract all text from a PDF supplied as bytes or a binary file object.

    Iterates over every page in the document, collects the text returned by
    pdfplumber, and joins the pages with newline characters.

    Args:
        source: Either a ``bytes`` object containing the raw PDF data, or any
            binary file-like object (i.e., an object with a ``read`` method
            that returns ``bytes``).

    Returns:
        A single string containing the concatenated text of all pages,
        separated by newline characters.

    Raises:
        PDFExtractionError: If the PDF is corrupt or cannot be opened,
            if the document is password-protected, or if no text can be
            extracted from any page (including blank / image-only PDFs).
        TypeError: If *source* is neither ``bytes`` nor a binary file-like
            object.
    """
    # Normalise the input to a seekable file-like object that pdfplumber
    # accepts.  When the caller passes raw bytes we wrap them in BytesIO so
    # the rest of the function is uniform.
    if isinstance(source, (bytes, bytearray)):
        file_obj: BinaryIO = io.BytesIO(source)
    elif hasattr(source, "read"):
        file_obj = source  # type: ignore[assignment]
    else:
        raise TypeError(
            f"source must be bytes or a binary file-like object, "
            f"got {type(source).__name__!r}"
        )

    try:
        with pdfplumber.open(file_obj) as pdf:
            # pdfplumber raises pdfminer.pdfdocument.PDFPasswordIncorrect (a
            # subclass of Exception) for encrypted PDFs with no empty
            # password.  We catch the broad Exception below and re-raise as
            # PDFExtractionError so callers only need to handle one type.
            page_texts: list[str] = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                page_texts.append(text)

    except Exception as exc:  # noqa: BLE001
        # Covers corrupt files, encrypted PDFs, and pdfminer parse errors.
        raise PDFExtractionError(
            f"Failed to open or parse PDF: {exc}"
        ) from exc

    combined = "\n".join(page_texts).strip()

    if not combined:
        raise PDFExtractionError(
            "PDF contains no extractable text. "
            "It may be image-only, blank, or password-protected."
        )

    return combined
