from openai import OpenAI

from config import PROXYAPI_API_KEY, PROXYAPI_BASE_URL, REQUEST_TIMEOUT_SECONDS


client = OpenAI(
    api_key=PROXYAPI_API_KEY or "missing-key",
    base_url=PROXYAPI_BASE_URL,
    timeout=REQUEST_TIMEOUT_SECONDS,
)
