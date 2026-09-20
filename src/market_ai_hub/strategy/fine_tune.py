"""Phase 2F — FineTuneAdapter interface（L）。

只提供 extension point。實際 enable：XGBoost / LightGBM / NHITS / NBEATSx。
Foundation models 預設 disabled。不得因 interface 存在就開始重度微調。
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class FineTuneAdapter(ABC):
    model_name: str = ""
    supported: bool = False
    foundation: bool = False

    @abstractmethod
    def prepare_dataset(self, *args, **kwargs):
        ...

    @abstractmethod
    def train(self, *args, **kwargs):
        ...

    @abstractmethod
    def evaluate(self, *args, **kwargs):
        ...

    @abstractmethod
    def save_artifact(self, *args, **kwargs):
        ...

    @abstractmethod
    def rollback(self, *args, **kwargs):
        ...


class XGBoostAdapter(FineTuneAdapter):
    model_name = "xgboost"
    supported = True
    foundation = False

    def prepare_dataset(self, *a, **k): raise NotImplementedError("extension point")
    def train(self, *a, **k): raise NotImplementedError("extension point")
    def evaluate(self, *a, **k): raise NotImplementedError("extension point")
    def save_artifact(self, *a, **k): raise NotImplementedError("extension point")
    def rollback(self, *a, **k): raise NotImplementedError("extension point")


class LightGBMAdapter(FineTuneAdapter):
    model_name = "lightgbm"
    supported = True
    foundation = False

    def prepare_dataset(self, *a, **k): raise NotImplementedError("extension point")
    def train(self, *a, **k): raise NotImplementedError("extension point")
    def evaluate(self, *a, **k): raise NotImplementedError("extension point")
    def save_artifact(self, *a, **k): raise NotImplementedError("extension point")
    def rollback(self, *a, **k): raise NotImplementedError("extension point")


class NHITSAdapter(FineTuneAdapter):
    model_name = "nhits"
    supported = True
    foundation = False

    def prepare_dataset(self, *a, **k): raise NotImplementedError("extension point")
    def train(self, *a, **k): raise NotImplementedError("extension point")
    def evaluate(self, *a, **k): raise NotImplementedError("extension point")
    def save_artifact(self, *a, **k): raise NotImplementedError("extension point")
    def rollback(self, *a, **k): raise NotImplementedError("extension point")


class NBEATSxAdapter(FineTuneAdapter):
    model_name = "nbeatsx"
    supported = True
    foundation = False

    def prepare_dataset(self, *a, **k): raise NotImplementedError("extension point")
    def train(self, *a, **k): raise NotImplementedError("extension point")
    def evaluate(self, *a, **k): raise NotImplementedError("extension point")
    def save_artifact(self, *a, **k): raise NotImplementedError("extension point")
    def rollback(self, *a, **k): raise NotImplementedError("extension point")


class FoundationModelAdapter(FineTuneAdapter):
    """Foundation models 預設 disabled。"""

    model_name = "foundation"
    supported = False
    foundation = True

    def prepare_dataset(self, *a, **k): raise NotImplementedError("disabled")
    def train(self, *a, **k): raise NotImplementedError("disabled")
    def evaluate(self, *a, **k): raise NotImplementedError("disabled")
    def save_artifact(self, *a, **k): raise NotImplementedError("disabled")
    def rollback(self, *a, **k): raise NotImplementedError("disabled")


_ADAPTERS: dict[str, FineTuneAdapter] = {
    "xgboost": XGBoostAdapter(),
    "lightgbm": LightGBMAdapter(),
    "nhits": NHITSAdapter(),
    "nbeatsx": NBEATSxAdapter(),
    # foundation（disabled）：kronos-tw / sundial / moirai-2 / ttm / timesfm / chronos
}


def get_adapter(model: str) -> FineTuneAdapter:
    a = _ADAPTERS.get(model)
    if a is not None:
        return a
    return FoundationModelAdapter()
