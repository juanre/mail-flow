from __future__ import annotations

from typing import Tuple
from mailflow.pdf_converter import text_to_pdf_bytes


def convert_attachment(
    filename: str, mimetype: str, content: bytes
) -> Tuple[str, bytes, str]:
    """Convert an attachment to archive-friendly format.

    Returns tuple of (target_mimetype, target_content, target_original_filename)
    where target_original_filename is used for extension inference when saving.
    """
    m = (mimetype or "").lower()
    name = filename or "attachment"

    # CSV stays CSV
    if m == "text/csv" or name.lower().endswith(".csv"):
        return "text/csv", content, name if name.lower().endswith(".csv") else f"{name}.csv"

    # TSV -> CSV
    if m == "text/tab-separated-values" or name.lower().endswith(".tsv"):
        text = content.decode("utf-8", errors="replace")
        csv_text = text.replace("\t", ",")
        base = name.rsplit(".", 1)[0]
        return "text/csv", csv_text.encode("utf-8"), f"{base}.csv"

    # Other text/* -> PDF
    if m.startswith("text/"):
        text = content.decode("utf-8", errors="replace")
        pdf = text_to_pdf_bytes(text)
        base = name.rsplit(".", 1)[0]
        return "application/pdf", pdf, f"{base}.pdf"

    # Otherwise, leave as-is (no conversion)
    return mimetype, content, filename
