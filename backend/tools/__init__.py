"""
backend/tools — utility tools for the CareerLens backend.

Public API
----------
extract_pdf_text   Extract plain text from a PDF (bytes or file-like object).
PDFExtractionError Raised when extraction fails (corrupt, empty, encrypted).
"""

from .pdf_extractor import PDFExtractionError, extract_pdf_text

__all__ = [
    "extract_pdf_text",
    "PDFExtractionError",
]
