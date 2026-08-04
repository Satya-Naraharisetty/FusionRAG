import os
from abc import ABC, abstractmethod

import yaml
from pydantic import BaseModel


class ModelPricing(BaseModel):
    input_cost_per_million: float
    output_cost_per_million: float


class BasePricingProvider(ABC):
    @abstractmethod
    def get_pricing(self, model_name: str) -> ModelPricing:
        """Retrieve inputs/outputs cost configuration for a model."""
        pass


class YAMLPricingProvider(BasePricingProvider):
    def __init__(self, file_path: str) -> None:
        self._file_path = file_path
        self._pricing_cache: dict[str, ModelPricing] = {}
        self._load_pricing()

    def _load_pricing(self) -> None:
        if not os.path.exists(self._file_path):
            self._set_fallbacks()
            return

        try:
            with open(self._file_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                models_data = data.get("models", {})
                for model, costs in models_data.items():
                    self._pricing_cache[model] = ModelPricing(
                        input_cost_per_million=costs.get("input_cost_per_million", 0.0),
                        output_cost_per_million=costs.get("output_cost_per_million", 0.0),
                    )
        except Exception:
            self._set_fallbacks()

    def _set_fallbacks(self) -> None:
        self._pricing_cache = {
            "gemini-1.5-flash": ModelPricing(
                input_cost_per_million=0.075, output_cost_per_million=0.30
            ),
            "gpt-4o-mini": ModelPricing(
                input_cost_per_million=0.15, output_cost_per_million=0.60
            ),
            "text-embedding-3-small": ModelPricing(
                input_cost_per_million=0.02, output_cost_per_million=0.02
            ),
        }

    def get_pricing(self, model_name: str) -> ModelPricing:
        return self._pricing_cache.get(
            model_name,
            ModelPricing(input_cost_per_million=0.0, output_cost_per_million=0.0),
        )
