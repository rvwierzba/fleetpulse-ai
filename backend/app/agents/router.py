"""Hybrid AI Router with Circuit Breaker and local Ollama routing."""

import json
import logging
import time
from typing import Any

import httpx

from app.agents.schemas import CircuitBreakerState, RouterMetrics
from app.infra.config import get_settings

logger = logging.getLogger("fleetpulse.router")


class HybridAIRouter:
    """Intelligent router directing LLM queries to local models with circuit protection."""

    def __init__(
        self,
        base_url: str | None = None,
        primary_model: str = "phi4-mini:latest",
        fallback_model: str = "llama3.1:8b",
        failure_threshold: int = 3,
        recovery_time_seconds: float = 30.0,
        timeout_seconds: float = 15.0,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.failure_threshold = failure_threshold
        self.recovery_time_seconds = recovery_time_seconds
        self.timeout_seconds = timeout_seconds

        # Circuit breaker internal state
        self._circuit_state: CircuitBreakerState = CircuitBreakerState.CLOSED
        self._consecutive_failures: int = 0
        self._last_state_change: float = time.time()

    @property
    def circuit_state(self) -> CircuitBreakerState:
        """Evaluate circuit breaker state considering recovery timeout."""
        now = time.time()
        if (
            self._circuit_state == CircuitBreakerState.OPEN
            and (now - self._last_state_change) >= self.recovery_time_seconds
        ):
            logger.info("Circuit breaker transition OPEN -> HALF_OPEN (probing primary)")
            self._circuit_state = CircuitBreakerState.HALF_OPEN
            self._last_state_change = now
        return self._circuit_state

    def _record_success(self) -> None:
        """Reset failures and close circuit upon successful primary response."""
        self._consecutive_failures = 0
        if self._circuit_state != CircuitBreakerState.CLOSED:
            logger.info("Circuit breaker transition %s -> CLOSED", self._circuit_state.value)
            self._circuit_state = CircuitBreakerState.CLOSED
            self._last_state_change = time.time()

    def _record_failure(self) -> None:
        """Increment failure counter and trip circuit open if threshold exceeded."""
        self._consecutive_failures += 1
        now = time.time()
        if (
            self._circuit_state in (CircuitBreakerState.CLOSED, CircuitBreakerState.HALF_OPEN)
            and self._consecutive_failures >= self.failure_threshold
        ):
            logger.warning(
                "Circuit breaker tripped OPEN (%d consecutive failures >= %d)",
                self._consecutive_failures,
                self.failure_threshold,
            )
            self._circuit_state = CircuitBreakerState.OPEN
            self._last_state_change = now

    async def _call_ollama(
        self,
        model: str,
        prompt: str,
        system_prompt: str,
    ) -> tuple[dict[str, Any], int | None, int | None]:
        """Invoke Ollama /api/generate with JSON format enforcement."""
        endpoint = f"{self.base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "system": system_prompt,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.1,
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(endpoint, json=payload)
            if response.status_code != 200:
                raise RuntimeError(
                    f"Ollama HTTP {response.status_code}: {response.text[:200]}"
                )

            data = response.json()
            raw_response = data.get("response", "")
            prompt_tokens = data.get("prompt_eval_count")
            completion_tokens = data.get("eval_count")

            parsed = json.loads(raw_response)
            if not isinstance(parsed, dict):
                raise ValueError(f"Expected JSON object from LLM, got {type(parsed).__name__}")
            return parsed, prompt_tokens, completion_tokens

    async def generate_json(
        self,
        prompt: str,
        system_prompt: str,
        force_fallback: bool = False,
    ) -> tuple[dict[str, Any], RouterMetrics]:
        """Execute structured JSON inference using primary or fallback model."""
        start_time = time.perf_counter()
        current_state = self.circuit_state
        use_fallback = force_fallback or (current_state == CircuitBreakerState.OPEN)

        model_to_use = self.fallback_model if use_fallback else self.primary_model
        fallback_triggered = use_fallback

        try:
            parsed, p_tokens, c_tokens = await self._call_ollama(
                model=model_to_use,
                prompt=prompt,
                system_prompt=system_prompt,
            )
            if not use_fallback:
                self._record_success()

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            metrics = RouterMetrics(
                model_used=model_to_use,
                latency_ms=round(latency_ms, 2),
                circuit_state=self._circuit_state,
                fallback_triggered=fallback_triggered,
                prompt_tokens=p_tokens,
                completion_tokens=c_tokens,
            )
            return parsed, metrics

        except Exception as exc:
            logger.warning(
                "Primary model '%s' failed (%s). Checking fallback capability.",
                model_to_use,
                exc,
            )
            if not use_fallback:
                self._record_failure()

                # Attempt immediate failover to fallback model if not already attempted
                try:
                    logger.info("Executing failover to model '%s'", self.fallback_model)
                    parsed, p_tokens, c_tokens = await self._call_ollama(
                        model=self.fallback_model,
                        prompt=prompt,
                        system_prompt=system_prompt,
                    )
                    latency_ms = (time.perf_counter() - start_time) * 1000.0
                    metrics = RouterMetrics(
                        model_used=self.fallback_model,
                        latency_ms=round(latency_ms, 2),
                        circuit_state=self._circuit_state,
                        fallback_triggered=True,
                        prompt_tokens=p_tokens,
                        completion_tokens=c_tokens,
                    )
                    return parsed, metrics
                except Exception as fallback_exc:
                    logger.error("Fallback model '%s' also failed: %s", self.fallback_model, fallback_exc)

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            raise RuntimeError(
                f"Hybrid AI Router failed to produce valid JSON output: {exc}"
            ) from exc


_router_instance: HybridAIRouter | None = None


def get_hybrid_ai_router() -> HybridAIRouter:
    """Return singleton HybridAIRouter."""
    global _router_instance
    if _router_instance is None:
        _router_instance = HybridAIRouter()
    return _router_instance
