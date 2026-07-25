"""Langfuse tracing setup for the LiveKit voice agent.

LiveKit Agents instruments each session with OpenTelemetry spans (STT, LLM,
TTS, turn-detection, tool calls, latency metrics). This module routes those
spans to Langfuse over the OpenTelemetry Protocol (OTLP), so every call gets
a full trace tree in the Langfuse dashboard.

Reference: https://docs.livekit.io/deploy/observability/tracing/
"""

import base64
import os
from typing import Optional

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.util.types import AttributeValue

from utils.logger import logger, redact_sensitive


def setup_langfuse(
    metadata: Optional[dict[str, AttributeValue]] = None,
) -> Optional[TracerProvider]:
    """Configure OpenTelemetry to export LiveKit agent spans to Langfuse.

    Reads LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and LANGFUSE_BASE_URL from
    the environment. If any are missing, tracing is skipped (returns None)
    instead of raising, so local dev / CI without Langfuse keys still runs.

    Call this once per job, before `AgentSession(...)` / `session.start(...)`,
    and register `trace_provider.force_flush` on the job's shutdown callback
    so buffered spans are sent before the worker process exits.
    """
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    base_url = os.environ.get("LANGFUSE_BASE_URL")

    if not public_key or not secret_key or not base_url:
        logger.warning(
            "[LANGFUSE] tracing disabled - set LANGFUSE_PUBLIC_KEY, "
            "LANGFUSE_SECRET_KEY, and LANGFUSE_BASE_URL to enable"
        )
        return None

    from livekit.agents.telemetry import set_tracer_provider
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    langfuse_auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = f"{base_url.rstrip('/')}/api/public/otel"
    os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=Basic {langfuse_auth}"

    trace_provider = TracerProvider()
    trace_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    set_tracer_provider(trace_provider, metadata=metadata)

    logger.info(
        "[LANGFUSE] tracing enabled, exporting to {}",
        redact_sensitive(base_url),
    )
    return trace_provider
