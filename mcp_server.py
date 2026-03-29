from mcp.server.fastmcp import FastMCP
import os, dotenv
import requests

dotenv.load_dotenv()

mcp = FastMCP("tools")

_HTTP_TIMEOUT = 15


@mcp.tool()
def get_transcript(url: str) -> str:
    """Get Youtube video transcript via Supadata API"""
    api_key = os.getenv("SUPADATA_API_KEY")
    if not api_key:
        raise ValueError("SUPADATA_API_KEY is not set")
    try:
        response = requests.get(
            "https://api.supadata.com/v1/youtube/transcript",
            params={"url": url.strip(), "text": True},
            headers={"x-api-key": api_key},
            timeout=_HTTP_TIMEOUT,
        )
    except requests.RequestException as e:
        return f"Supadata request failed: {e}"
    try:
        data = response.json()
    except Exception:
        return f"Supadata error (non-JSON body, HTTP {response.status_code})"
    if not response.ok or "content" not in data:
        return f"Transcript error: {data}"
    raw = data["content"]
    if isinstance(raw, list):
        text = " ".join(item["text"].replace("\n", " ") for item in raw)
    else:
        text = str(raw).replace("\n", " ")
    return text[:6000] if text.strip() else "Empty transcript content from Supadata."


@mcp.tool()
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression"""
    try:
        result = eval(expression)
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.tool()
def get_weather(city: str) -> str:
    """Get weather information for a city"""
    geo = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1},
        timeout=_HTTP_TIMEOUT,
    ).json()
    if not geo or "results" not in geo or not geo["results"]:
        return f"No weather data found for {city}"
    lat = geo["results"][0]["latitude"]
    lon = geo["results"][0]["longitude"]
    name = geo["results"][0]["name"]
    weather = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,wind_speed_10m",
        },
        timeout=_HTTP_TIMEOUT,
    ).json()
    cur = weather.get("current") or {}
    if "temperature_2m" not in cur:
        return f"No weather data found for {city}"
    temperature = cur["temperature_2m"]
    wind = cur.get("wind_speed_10m")
    if wind is not None:
        return f"{name} : {temperature}°C, wind {wind} km/h"
    return f"{name} : {temperature}°C"


if __name__ == "__main__":
    mcp.run(transport="stdio")
