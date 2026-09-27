"""
OpenTelemetry adapter (Plan Step 91): the first concrete Telemetry.

Like every other adapter, this is the ONLY file allowed to import
`opentelemetry` -- core/memory_os depends only on telemetry.py's
Telemetry Protocol.

Defaults to in-memory exporters (InMemorySpanExporter/
InMemoryMetricReader) so tests -- and this codebase's own gate checks --
can assert on what was actually recorded without a collector running
anywhere. A real deployment passes its own exporter/reader (OTLP, etc.)
via the same constructor parameters.
"""

from __future__ import annotations

from contextlib import contextmanager

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


class OTelTelemetry:
    """Implements memory_os.telemetry.Telemetry."""

    def __init__(self, *, span_exporter=None, metric_reader=None, service_name: str = "memory-os"):
        self.span_exporter = span_exporter if span_exporter is not None else InMemorySpanExporter()
        self.metric_reader = metric_reader if metric_reader is not None else InMemoryMetricReader()

        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(SimpleSpanProcessor(self.span_exporter))
        self._tracer = tracer_provider.get_tracer(service_name)

        meter_provider = MeterProvider(metric_readers=[self.metric_reader])
        self._meter = meter_provider.get_meter(service_name)
        self._instruments: dict = {}

    @contextmanager
    def span(self, name: str, **attributes):
        with self._tracer.start_as_current_span(name, attributes=attributes):
            yield

    def record_metric(self, name: str, value: float, **attributes) -> None:
        # A histogram, not a counter: Step 92's metrics (Recall@K,
        # contradiction rate, ...) are arbitrary numeric observations,
        # not monotonically-increasing counts -- a Counter instrument
        # would reject a value like a dropping recall score outright.
        if name not in self._instruments:
            self._instruments[name] = self._meter.create_histogram(name)
        self._instruments[name].record(value, attributes=attributes)

    def exported_spans(self):
        """Test/inspection helper over the default in-memory exporter."""
        return self.span_exporter.get_finished_spans()

    def collected_metrics(self):
        """Test/inspection helper over the default in-memory reader."""
        return self.metric_reader.get_metrics_data()
