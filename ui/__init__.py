# ui/__init__.py
"""
GRA-MicroAnalyzer 鈥� UI package.

Do NOT import MainWindow here.  ui.main_window imports from ui.threads
and ui.widgets, so any eager import at package-init level creates a
circular import chain that prevents the entire package from loading.

Correct usage in main.py::

    from ui.main_window import MainWindow

__all__ is intentionally empty 鈥� the package acts purely as a namespace.
"""

__all__: list[str] = []
