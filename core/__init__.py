# core/__init__.py
"""
GRA-MicroAnalyzer — Core Package
=================================
Exposes the primary domain objects and computation engine at the
package level so that importing code can write:

    from core import GreyRelationalAnalyzer, GRAConfig, GRAResult
"""

from core.exceptions import (
    GRABaseException,
    DataLoadError,
    InsufficientDataError,
    ColumnNotFoundError,
    PolarityConfigError,
    NormalizationError,
    ComputationError,
)
from core.data_model import Polarity, ColumnConfig, GRAConfig, GRAResult
from core.gra_engine import GreyRelationalAnalyzer

__all__: list[str] = [
    # Exceptions
    "GRABaseException",
    "DataLoadError",
    "InsufficientDataError",
    "ColumnNotFoundError",
    "PolarityConfigError",
    "NormalizationError",
    "ComputationError",
    # Data models
    "Polarity",
    "ColumnConfig",
    "GRAConfig",
    "GRAResult",
    # Engine
    "GreyRelationalAnalyzer",
]
