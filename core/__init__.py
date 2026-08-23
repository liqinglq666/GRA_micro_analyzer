# core/__init__.py
"""
GRA-MicroAnalyzer — Core Package
=================================
Exposes the primary domain objects and computation engine at the package level.
"""

from core.exceptions import (
    GRABaseException,
    DataLoadError,
    InsufficientDataError,
    ColumnNotFoundError,
    PolarityConfigError,
    DuplicateColumnError,
    NormalizationError,
    ComputationError,
)
from core.data_model import Polarity, ColumnConfig, GRAConfig, GRAResult
from core.gra_engine import GreyRelationalAnalyzer

__all__: list[str] = [
    "GRABaseException",
    "DataLoadError",
    "InsufficientDataError",
    "ColumnNotFoundError",
    "PolarityConfigError",
    "DuplicateColumnError",
    "NormalizationError",
    "ComputationError",
    "Polarity",
    "ColumnConfig",
    "GRAConfig",
    "GRAResult",
    "GreyRelationalAnalyzer",
]
