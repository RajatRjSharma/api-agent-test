import logging
import time
from mcp.server.fastmcp import FastMCP
import os, dotenv
import requests

dotenv.load_dotenv()

_level_name = (os.getenv("LOG_LEVEL") or "INFO").upper()
_level = getattr(logging, _level_name, logging.INFO)
logging.basicConfig(
    level=_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)
logger = logging.getLogger(__name__)

mcp = FastMCP("tools")

_HTTP_TIMEOUT = 15
# Official API: GET https://api.supadata.ai/v1/transcript?url=...&text=true (not POST — POST returns 404).
_SUPADATA_BASE = "https://api.supadata.ai/v1"
_LOG_BODY_MAX = 12000


def _format_transcript_content(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.replace("\n", " ").strip()
    if isinstance(raw, list):
        parts = []
        for item in raw:
            if isinstance(item, dict) and "text" in item:
                parts.append(item["text"].replace("\n", " "))
            else:
                parts.append(str(item).replace("\n", " "))
        return " ".join(parts).strip()
    return str(raw).replace("\n", " ").strip()


def _poll_transcript_job(api_key: str, job_id: str) -> tuple[str | None, str | None]:
    """Poll GET /v1/transcript/{jobId} until completed, failed, or timeout."""
    max_sec = int(os.getenv("SUPADATA_JOB_TIMEOUT_SEC") or "120")
    interval = float(os.getenv("SUPADATA_JOB_POLL_SEC") or "2")
    poll_url = f"{_SUPADATA_BASE}/transcript/{job_id}"
    headers = {"x-api-key": api_key}
    deadline = time.time() + max_sec
    while time.time() < deadline:
        try:
            r = requests.get(poll_url, headers=headers, timeout=_HTTP_TIMEOUT)
        except requests.RequestException as e:
            logger.exception("Supadata job poll request failed job_id=%s", job_id)
            return None, f"Job poll request failed: {e}"
        try:
            data = r.json()
        except Exception:
            logger.error(
                "Job poll non-JSON HTTP %s body=%s",
                r.status_code,
                (r.text or "")[:2000],
            )
            return None, f"Job poll non-JSON (HTTP {r.status_code})"
        if not r.ok:
            return None, f"Job poll HTTP {r.status_code}: {data}"
        status = data.get("status")
        if status == "completed":
            text = _format_transcript_content(data.get("content"))
            if text:
                return text[:6000], None
            return None, "Job completed but transcript content was empty"
        if status == "failed":
            err = data.get("error")
            return None, f"Transcript job failed: {err}"
        if status in ("queued", "active", None):
            time.sleep(interval)
            continue
        return None, f"Unknown job status {status!r}: {data}"
    return None, f"Transcript job timed out after {max_sec}s (job_id={job_id})"


@mcp.tool()
def get_transcript(url: str) -> str:
    """Get Youtube video transcript via Supadata API (GET /v1/transcript per docs)."""
    api_key = os.getenv("SUPADATA_API_KEY")
    if not api_key:
        logger.error("get_transcript: SUPADATA_API_KEY is not set")
        raise ValueError("SUPADATA_API_KEY is not set")
    params = {
        "url": url.strip(),
        "text": "true",
        "mode": (os.getenv("SUPADATA_MODE") or "auto").strip() or "auto",
    }
    lang = (os.getenv("SUPADATA_LANG") or "").strip()
    if lang:
        params["lang"] = lang
    try:
        response = requests.get(
            f"{_SUPADATA_BASE}/transcript",
            params=params,
            headers={"x-api-key": api_key},
            timeout=_HTTP_TIMEOUT,
        )
    except requests.RequestException as e:
        logger.exception(
            "Supadata request failed type=%s repr=%r str=%s",
            type(e).__name__,
            e,
            e,
        )
        return f"Supadata request failed: {e}"
    try:
        data = response.json()
    except Exception as e:
        body = (response.text or "")[:_LOG_BODY_MAX]
        logger.exception(
            "Supadata JSON parse failed HTTP %s exc_type=%s body=%s",
            response.status_code,
            type(e).__name__,
            body,
        )
        return f"Supadata error (non-JSON body, HTTP {response.status_code})"
    if not response.ok:
        logger.error(
            "Supadata API error HTTP %s data=%r",
            response.status_code,
            data,
        )
        return f"Transcript error: {data}"

    if "content" in data:
        text = _format_transcript_content(data["content"])
        if text:
            logger.info("get_transcript ok length=%s lang=%r", len(text), data.get("lang"))
            return text[:6000]
        if not data.get("jobId"):
            logger.warning("Supadata returned empty content (sync)")
            return "Empty transcript content from Supadata."

    if data.get("jobId"):
        logger.info("Supadata async job jobId=%s — polling for result", data["jobId"])
        text, err = _poll_transcript_job(api_key, data["jobId"])
        if text:
            logger.info("get_transcript ok (async) length=%s", len(text))
            return text
        logger.error("Supadata async job failed: %s", err)
        return err or "Transcript job failed."

    logger.error("Supadata unexpected JSON: %r", data)
    return f"Transcript error (unexpected response): {data}"


@mcp.tool()
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression"""
    try:
        result = eval(expression)
        return f"{expression} = {result}"
    except Exception as e:
        logger.error(
            "calculate failed expr=%r type=%s repr=%r str=%s",
            expression,
            type(e).__name__,
            e,
            e,
            exc_info=True,
        )
        return f"Error: {str(e)}"


@mcp.tool()
def get_weather(city: str) -> str:
    """Get weather information for a city"""
    try:
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1},
            timeout=_HTTP_TIMEOUT,
        )
        geo.raise_for_status()
        geo = geo.json()
    except requests.RequestException as e:
        logger.exception(
            "get_weather geocoding failed city=%r type=%s repr=%r str=%s",
            city,
            type(e).__name__,
            e,
            e,
        )
        return f"Weather lookup failed (geocoding): {e}"
    if not geo or "results" not in geo or not geo["results"]:
        logger.warning("get_weather: no geocoding results for %r", city)
        return f"No weather data found for {city}"
    lat = geo["results"][0]["latitude"]
    lon = geo["results"][0]["longitude"]
    name = geo["results"][0]["name"]
    try:
        weather = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,wind_speed_10m",
            },
            timeout=_HTTP_TIMEOUT,
        )
        weather.raise_for_status()
        weather = weather.json()
    except requests.RequestException as e:
        logger.exception(
            "get_weather forecast failed city=%r type=%s repr=%r str=%s",
            city,
            type(e).__name__,
            e,
            e,
        )
        return f"Weather lookup failed (forecast): {e}"
    cur = weather.get("current") or {}
    if "temperature_2m" not in cur:
        logger.warning("get_weather: no current temperature for %r", city)
        return f"No weather data found for {city}"
    temperature = cur["temperature_2m"]
    wind = cur.get("wind_speed_10m")
    if wind is not None:
        return f"{name} : {temperature}°C, wind {wind} km/h"
    return f"{name} : {temperature}°C"


if __name__ == "__main__":
    mcp.run(transport="stdio")
