"""Make litrag importable and hermetic for tests."""
import sys
import types as _stdlib_types
from pathlib import Path
from unittest import mock

import pytest

LITRAG_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _litrag_importable():
    if str(LITRAG_DIR) not in sys.path:
        sys.path.insert(0, str(LITRAG_DIR))
    fake_pdfium = _stdlib_types.ModuleType("pypdfium2")
    fake_pdfium.PdfDocument = mock.MagicMock()
    with mock.patch.dict("sys.modules", {"pypdfium2": fake_pdfium}):
        yield
