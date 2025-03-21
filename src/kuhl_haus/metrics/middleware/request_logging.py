from __future__ import annotations

import time
import traceback

from fastapi import Request

from kuhl_haus.metrics.data.metrics import Metrics
from kuhl_haus.metrics.recorders.graphite_logger import GraphiteLogger


async def request_metrics(
        request: Request,
        call_next,
        recorder: GraphiteLogger,
):
    mnemonic = request.url.path.replace("/", "_")
    if mnemonic.startswith("_"):
        mnemonic = mnemonic[1:]  # Remove the leading underscore
    metrics: Metrics = recorder.get_metrics(mnemonic=mnemonic, hostname=request.headers['host'])
    try:
        start_time = time.perf_counter_ns()
        response = await call_next(request)
        request_time = time.perf_counter_ns() - start_time

        metrics.set_counter('responses', 1)
        response.headers["X-Request-Time"] = str(request_time)
        response.headers["X-Request-Time-MS"] = str(request_time // 1_000_000)
        metrics.attributes['request_time'] = int(request_time)
        metrics.attributes['request_time_ms'] = int(request_time // 1_000_000)

        if "Content-Length" in response.headers:
            metrics.attributes['response_length'] = response.headers["Content-Length"]

        start_metric_time = time.perf_counter_ns()
        recorder.log_metrics(metrics)
        metric_time = time.perf_counter_ns() - start_metric_time

        response.headers["X-Metrics-Time"] = str(metric_time)
        response.headers["X-Metrics-Time-MS"] = str(metric_time // 1_000_000)

        return response
    except Exception as e:
        metrics.attributes['exception'] = repr(e)
        metrics.set_counter('exceptions', 1)
        recorder.log_metrics(metrics)
        recorder.logger.error(
            f"Unhandled exception raised while processing {mnemonic} request: ({repr(e)})\r\n"
            f"{traceback.format_exc()}"
        )
        raise e
