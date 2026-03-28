"""
LLM Model Discovery — queries LocalAI for available models.

This module provides runtime discovery of LLM models from LocalAI,
allowing the WebUI to list available models and change the default
without restarting the service.

Usage:
    discovery = LLMModelDiscovery(localai_base_url="http://127.0.0.1:8080")
    models = discovery.list_models()
    for model in models:
        print(f"{model.id}: {model.name}")
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMModel:
    """Represents an LLM model available in LocalAI."""
    id: str
    name: str
    size: str | None = None
    format: str | None = None
    family: str | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for API response."""
        return {
            "id": self.id,
            "name": self.name,
            "size": self.size,
            "format": self.format,
            "family": self.family,
            "parameter_size": self.parameter_size,
            "quantization": self.quantization,
        }


@dataclass
class LLMStatus:
    """LLM service status."""
    available: bool
    localai_url: str
    default_model: str | None
    models_count: int
    error: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for API response."""
        return {
            "available": self.available,
            "localai_url": self.localai_url,
            "default_model": self.default_model,
            "models_count": self.models_count,
            "error": self.error,
        }


class LLMModelDiscovery:
    """Discovers and manages LLM models from LocalAI."""
    
    def __init__(self, localai_base_url: str = "http://127.0.0.1:8080") -> None:
        self.base_url = localai_base_url.rstrip("/")
    
    def list_models(self) -> list[LLMModel]:
        """
        GET /v1/models from LocalAI.
        
        Returns:
            List of LLMModel objects.
        
        Raises:
            RuntimeError: If LocalAI is unavailable.
        """
        try:
            request = urllib.request.Request(
                url=f"{self.base_url}/v1/models",
                headers={"Content-Type": "application/json"},
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=10) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LocalAI unavailable at {self.base_url}: {exc.reason}") from exc
        except TimeoutError:
            raise RuntimeError(f"LocalAI timeout at {self.base_url}")
        except Exception as exc:
            raise RuntimeError(f"LocalAI error: {exc}") from exc
        
        result = json.loads(body)
        models = []
        for item in result.get("data", []):
            models.append(
                LLMModel(
                    id=item.get("id", ""),
                    name=item.get("name", item.get("id", "")),
                    size=item.get("size"),
                    format=item.get("format"),
                    family=item.get("family"),
                    parameter_size=item.get("parameter_size"),
                    quantization=item.get("quantization"),
                )
            )
        return models
    
    def get_default_model(self) -> str | None:
        """
        Get current default model from LocalAI config.
        
        Returns:
            Default model ID or None if unavailable.
        """
        try:
            request = urllib.request.Request(
                url=f"{self.base_url}/v1/config",
                headers={"Content-Type": "application/json"},
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=10) as resp:
                body = resp.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, Exception):
            return None
        
        result = json.loads(body)
        return result.get("default_model")
    
    def set_default_model(self, model_id: str) -> bool:
        """
        Set default model in LocalAI config.
        
        Args:
            model_id: The model ID to set as default.
        
        Returns:
            True if successful, False otherwise.
        """
        try:
            payload = json.dumps({"default_model": model_id}).encode("utf-8")
            request = urllib.request.Request(
                url=f"{self.base_url}/v1/config",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
            with urllib.request.urlopen(request, timeout=10) as resp:
                return resp.status == 200
        except (urllib.error.URLError, TimeoutError, Exception):
            return False
    
    def get_status(self) -> LLMStatus:
        """
        Get comprehensive LLM service status.
        
        Returns:
            LLMStatus object with availability and model info.
        """
        try:
            models = self.list_models()
            default_model = self.get_default_model()
            return LLMStatus(
                available=True,
                localai_url=self.base_url,
                default_model=default_model,
                models_count=len(models),
            )
        except RuntimeError as exc:
            return LLMStatus(
                available=False,
                localai_url=self.base_url,
                default_model=None,
                models_count=0,
                error=str(exc),
            )


# Convenience function for quick discovery
def discover_models(localai_base_url: str = "http://127.0.0.1:8080") -> list[dict[str, Any]]:
    """
    Quick discovery of available models.
    
    Args:
        localai_base_url: LocalAI base URL.
    
    Returns:
        List of model dictionaries.
    """
    discovery = LLMModelDiscovery(localai_base_url)
    try:
        models = discovery.list_models()
        return [m.to_dict() for m in models]
    except RuntimeError:
        return []
