import logging
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
# Docs: POST https://api.supadata.ai/v1/transcript with JSON body (not the old .com GET endpoint).
_SUPADATA_URL = "https://api.supadata.ai/v1/transcript"
_LOG_BODY_MAX = 12000


@mcp.tool()
def get_transcript(url: str) -> str:
    """Get Youtube video transcript via Supadata API"""
    api_key = os.getenv("SUPADATA_API_KEY")
    if not api_key:
        logger.error("get_transcript: SUPADATA_API_KEY is not set")
        raise ValueError("SUPADATA_API_KEY is not set")
    payload = {"url": url.strip(), "text": True}
    lang = (os.getenv("SUPADATA_LANG") or "").strip()
    if lang:
        payload["lang"] = lang
    try:
        response = requests.post(
            _SUPADATA_URL,
            headers={
                "x-api-key": api_key,
                "Content-Type": "application/json",
            },
            json=payload,
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
    if not response.ok or "content" not in data:
        logger.error(
            "Supadata API error HTTP %s ok=%s data=%r",
            response.status_code,
            response.ok,
            data,
        )
        return f"Transcript error: {data}"
    raw = data["content"]
    if isinstance(raw, list):
        text = " ".join(item["text"].replace("\n", " ") for item in raw)
    else:
        text = str(raw).replace("\n", " ")
    text = text.strip()
    if not text:
        logger.warning("Supadata returned empty transcript content")
        return "Empty transcript content from Supadata."
    logger.info("get_transcript ok length=%s name=%r", len(text), data.get("name"))
    return text[:6000]


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
