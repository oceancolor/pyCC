"""Analytics config. Ported from services/analytics/config.ts"""
import os

ANALYTICS_ENDPOINT = os.environ.get("ANALYTICS_ENDPOINT", "")
ANALYTICS_API_KEY = os.environ.get("ANALYTICS_API_KEY", "")
