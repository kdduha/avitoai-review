"""Слой доступа к моделям.

Единственное место в кодовой базе, откуда уходят сетевые запросы к LLM.
Импорт провайдеров и сетевых библиотек вне этого пакета запрещён и
проверяется тестом `test_llm_is_the_only_exit`.
"""

from .audit import AuditLog, AuditRecord
from .gateway import GatewayResult, PrivacyGateway, fake_gateway, gateway_from_env
from .providers import (
    FakeProvider,
    LLMError,
    LLMResponse,
    LLMUnavailable,
    OpenAICompatibleProvider,
    Provider,
    provider_from_env,
)
from .routing import DataClass, RoutePolicy, TaskKind
from .scrub import Scrubber, residual_risk
from .structured import StructuredError, complete_json

__all__ = [
    "AuditLog",
    "AuditRecord",
    "DataClass",
    "FakeProvider",
    "GatewayResult",
    "LLMError",
    "LLMResponse",
    "LLMUnavailable",
    "OpenAICompatibleProvider",
    "PrivacyGateway",
    "Provider",
    "RoutePolicy",
    "Scrubber",
    "StructuredError",
    "TaskKind",
    "complete_json",
    "fake_gateway",
    "gateway_from_env",
    "provider_from_env",
    "residual_risk",
]
