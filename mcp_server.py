from mcp.server.fastmcp import FastMCP
import os, dotenv
import httpx

dotenv.load_dotenv()

mcp = FastMCP("tools")

_HTTP_TIMEOUT = httpx.Timeout(15.0)


@mcp.tool()
def get_transcript(url: str) -> str:
    """Get Youtube video transcript via Supadata API"""
    api_key = os.getenv("SUPADATA_API_KEY")
    if not api_key:
        raise ValueError("SUPADATA_API_KEY is not set")
    response = httpx.get(
        "https://api.supadata.com/v1/youtube/transcript",
        params={"url": url, "text": True},
        headers={"x-api-key": api_key},
        timeout=_HTTP_TIMEOUT,
    )
    data = response.json()
    if not response.is_success or "content" not in data:
        return f"Transcript error : {data}"
    raw = data["content"]
    if isinstance(raw, list):
        text = " ".join([item["text"].replace("\n", " ") for item in raw])
    else:
        text = raw.replace("\n", " ")
    return text[:6000]


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
    geo = httpx.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1},
        timeout=_HTTP_TIMEOUT,
    ).json()
    if not geo or "results" not in geo or not geo["results"]:
        return f"No weather data found for {city}"
    lat = geo["results"][0]["latitude"]
    lon = geo["results"][0]["longitude"]
    name = geo["results"][0]["name"]
    weather = httpx.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m",
            "hourly": "temperature_2m",
        },
        timeout=_HTTP_TIMEOUT,
    ).json()
    if (
        not weather
        or "current" not in weather
        or "temperature_2m" not in weather["current"]
    ):
        return f"No weather data found for {city}"
    temperature = weather["current"]["temperature_2m"]
    wind = weather["current"]["windspeed"]
    return f"{name} : {temperature}°C, wind {wind} km/h"


if __name__ == "__main__":
    mcp.run(transport="stdio")
