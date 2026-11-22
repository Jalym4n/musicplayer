import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole test run (Qt allows only one)."""
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])
