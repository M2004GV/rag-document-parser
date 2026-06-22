# ocr.py
"""Fallback de OCR para faturas escaneadas (item 9).

Quando um PDF é apenas imagem (digitalização), o PyPDFLoader devolve pouco ou
nenhum texto. Aqui rasterizamos as páginas com pdf2image e rodamos pytesseract.

Dependências de sistema: ``tesseract-ocr`` (com ``tesseract-ocr-por``) e
``poppler-utils``. Se algo faltar, as funções degradam para string vazia em vez
de quebrar a aplicação.
"""
from typing import Optional


def ocr_available() -> bool:
    """True se pytesseract, pdf2image e o binário do tesseract estão presentes."""
    try:
        import pytesseract  # noqa: F401
        import pdf2image  # noqa: F401
    except ImportError:
        return False
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def needs_ocr(text: str, min_chars: int = 40) -> bool:
    """Heurística: texto extraído curto demais sugere PDF só-imagem."""
    return len((text or "").strip()) < min_chars


def ocr_pdf(pdf_path: str, lang: str = "por", max_pages: int = 10) -> str:
    """Extrai texto de um PDF via OCR. Retorna '' se OCR indisponível/falhar."""
    if not ocr_available():
        return ""
    try:
        import pytesseract
        from pdf2image import convert_from_path

        images = convert_from_path(pdf_path, dpi=200, first_page=1, last_page=max_pages)
        chunks = []
        for img in images:
            chunks.append(pytesseract.image_to_string(img, lang=lang))
        return "\n\n".join(chunks)
    except Exception:
        return ""


def load_pdf_text_with_ocr_fallback(pdf_path: str) -> str:
    """Carrega texto do PDF; cai para OCR se o texto nativo for insuficiente."""
    text = ""
    try:
        from langchain_community.document_loaders import PyPDFLoader

        pages = PyPDFLoader(pdf_path).load_and_split()
        text = "\n\n".join(p.page_content for p in pages)
    except Exception:
        text = ""

    if needs_ocr(text):
        ocr_text = ocr_pdf(pdf_path)
        if ocr_text.strip():
            return ocr_text
    return text
