"""
bigquery_exporter.py - BigQuery metrics exporter for OpenTelemetry.

Port of TypeScript bigqueryExporter.ts.
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 5000
DEFAULT_METRICS_EXPORT_INTERVAL_MS = 5 * 60 * 1000  # 5 minutes


class BigQueryMetricsExporter:
    """
    Exports Claude Code metrics to BigQuery via the Anthropic metrics API.
    """

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        default_endpoint = 'https://api.anthropic.com/api/claude_code/metrics'

        if (os.environ.get('USER_TYPE') == 'ant'
                and os.environ.get('ANT_CLAUDE_CODE_METRICS_ENDPOINT')):
            self.endpoint = (
                os.environ['ANT_CLAUDE_CODE_METRICS_ENDPOINT']
                + '/api/claude_code/metrics'
            )
        else:
            self.endpoint = default_endpoint

        self.timeout = timeout / 1000  # Convert to seconds
        self._pending_exports: List[asyncio.Task] = []
        self._is_shutdown = False

    async def export(self, metrics: Any) -> bool:
        """Export metrics. Returns True on success, False on failure."""
        if self._is_shutdown:
            logger.debug('BigQuery metrics exporter: shutdown, skipping')
            return False

        try:
            return await self._do_export(metrics)
        except Exception as e:
            logger.debug(f'BigQuery metrics export failed: {e}')
            return False

    async def _do_export(self, metrics: Any) -> bool:
        try:
            from ...utils.config import check_has_trust_dialog_accepted
            from ...bootstrap.state import get_is_non_interactive_session
            has_trust = (
                check_has_trust_dialog_accepted()
                or get_is_non_interactive_session()
            )
            if not has_trust:
                return True  # Skip silently
        except ImportError:
            pass

        try:
            from ...services.api.logging import check_metrics_enabled
            metrics_status = await check_metrics_enabled()
            if not metrics_status.get('enabled', True):
                logger.debug('Metrics export disabled by organization setting')
                return True
        except ImportError:
            pass

        payload = self._transform_metrics(metrics)

        try:
            import httpx
            from ...utils.http import get_auth_headers

            auth_result = get_auth_headers()
            if auth_result.get('error'):
                return False

            headers = {
                'Content-Type': 'application/json',
                **auth_result.get('headers', {}),
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.endpoint,
                    content=json.dumps(payload),
                    headers=headers,
                )
                response.raise_for_status()
            logger.debug('BigQuery metrics exported successfully')
            return True
        except Exception as e:
            logger.debug(f'BigQuery metrics export failed: {e}')
            return False

    def _transform_metrics(self, metrics: Any) -> Dict:
        """Transform OTel metrics to BigQuery format."""
        resource_attrs = getattr(getattr(metrics, 'resource', None), 'attributes', {}) or {}

        resource_attributes = {
            'service.name': str(resource_attrs.get('service.name', 'claude-code')),
            'service.version': str(resource_attrs.get('service.version', 'unknown')),
            'os.type': str(resource_attrs.get('os.type', 'unknown')),
            'os.version': str(resource_attrs.get('os.version', 'unknown')),
            'host.arch': str(resource_attrs.get('host.arch', 'unknown')),
            'aggregation.temporality': 'delta',
        }

        if resource_attrs.get('wsl.version'):
            resource_attributes['wsl.version'] = str(resource_attrs['wsl.version'])

        scope_metrics = getattr(metrics, 'scope_metrics', []) or []
        transformed_metrics = []
        for scope_metric in scope_metrics:
            for metric in getattr(scope_metric, 'metrics', []):
                descriptor = getattr(metric, 'descriptor', None)
                transformed_metrics.append({
                    'name': getattr(descriptor, 'name', ''),
                    'description': getattr(descriptor, 'description', ''),
                    'unit': getattr(descriptor, 'unit', ''),
                    'data_points': self._extract_data_points(metric),
                })

        return {
            'resource_attributes': resource_attributes,
            'metrics': transformed_metrics,
        }

    def _extract_data_points(self, metric: Any) -> List[Dict]:
        """Extract data points from a metric."""
        data_points = getattr(metric, 'data_points', []) or []
        result = []
        for point in data_points:
            value = getattr(point, 'value', None)
            if not isinstance(value, (int, float)):
                continue

            end_time = getattr(point, 'end_time', None)
            timestamp = self._hrtime_to_iso(end_time) if end_time else _current_iso()

            result.append({
                'attributes': {
                    k: str(v)
                    for k, v in (getattr(point, 'attributes', {}) or {}).items()
                    if v is not None
                },
                'value': value,
                'timestamp': timestamp,
            })
        return result

    def _hrtime_to_iso(self, hrtime: Any) -> str:
        """Convert high-resolution time to ISO string."""
        try:
            if isinstance(hrtime, (list, tuple)) and len(hrtime) >= 2:
                seconds, nanoseconds = hrtime[0], hrtime[1]
                ms = seconds * 1000 + nanoseconds / 1_000_000
            else:
                ms = float(hrtime) * 1000 if hrtime else time.time() * 1000
            from datetime import datetime, timezone
            return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
        except Exception:
            return _current_iso()

    async def shutdown(self) -> None:
        """Shutdown the exporter."""
        self._is_shutdown = True
        await self.force_flush()

    async def force_flush(self) -> None:
        """Force flush any pending exports."""
        if self._pending_exports:
            await asyncio.gather(*self._pending_exports, return_exceptions=True)
            self._pending_exports.clear()


def _current_iso() -> str:
    """Get current time as ISO string."""
    from datetime import datetime, timezone
    return datetime.now(tz=timezone.utc).isoformat()
