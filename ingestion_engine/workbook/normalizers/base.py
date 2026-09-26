"""Base sheet normalizer."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from ingestion_engine.contractor import ContractorSelector


class SheetNormalizer(ABC):
    canonical_name: str

    def __init__(self, contractor_selector: ContractorSelector | None = None):
        self.contractor = contractor_selector or ContractorSelector()

    @abstractmethod
    def normalize(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame: ...
