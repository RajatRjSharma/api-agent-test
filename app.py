import os, json, dotenv
import logging
import gradio as gr
from fastapi import FastAPI
from openai import OpenAI
from mcp_server import get_transcript, calculate, get_weather
import uvicorn


dotenv.load_dotenv()

logger = logging.getLogger("app")

# Avoid flooding logs; errors are logged in full up to this length.
_MAX_TOOL_LOG_CHARS = 50000

TOOLS = {
    "get_transcript": get_transcript,
    "calculate": calculate,
    "get_weather": get_weather,
}

SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_transcript",
            "description": "Get the transcript of a Youtube video",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL of the Youtube video",
                    }
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Calculate a mathematical expression",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The mathematical expression to calculate",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the weather information for a city",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "The name of the city"}
                },
                "required": ["city"],
            },
        },
    },
]


def run(url, query):
    logger.info(
        "run() start query_len=%s has_url=%s",
        len(query or ""),
        bool(url and str(url).strip()),
    )
    try:
        api_key = os.getenv("OPENROUTER_API_KEY")
        base_url = os.getenv("OPENROUTER_BASE_URL")
        if not api_key or not base_url:
            logger.error("OPENROUTER_API_KEY or OPENROUTER_BASE_URL is not set")
            raise ValueError("OPENROUTER_API_KEY is not set")
        client = OpenAI(api_key=api_key, base_url=base_url)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. When a tool returns a result, use it to answer. "
                    "Only call get_transcript when the user needs a Youtube transcript. "
                    "If a tool returns an error string (e.g. starting with 'Supadata' or 'Transcript error'), "
                    "quote that exact message to the user—do not replace it with vague phrases like "
                    "'connection error' or 'try again later' unless the tool text says so."
                ),
            },
            {
                "role": "user",
                "content": (f"URL: {url}\n\n" if (url or "").strip() else "") + (query or ""),
            },
        ]

        while True:
            try:
                response = client.chat.completions.create(
                    model="openai/gpt-4o-mini",
                    messages=messages,
                    tools=SCHEMAS,
                    tool_choice="auto",
                )
            except Exception as e:
                extra = f"type={type(e).__name__!s} str={e!s} repr={e!r}"
                if hasattr(e, "status_code"):
                    extra += f" status_code={getattr(e, 'status_code', None)!r}"
                if hasattr(e, "body"):
                    extra += f" body={getattr(e, 'body', None)!r}"
                if hasattr(e, "response") and getattr(e, "response", None) is not None:
                    try:
                        rt = e.response.text
                        extra += f" response_text[:8000]={rt[:8000]!r}"
                    except Exception:
                        pass
                logger.exception("OpenAI chat.completions.create failed: %s", extra)
                raise
            message = response.choices[0].message
            if not message.tool_calls:
                logger.info("run() completed (assistant message, no tools)")
                return message.content

            messages.append(message)

            for tool_call in message.tool_calls:
                name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    logger.exception("Invalid JSON for tool %s: %r", name, tool_call.function.arguments)
                    raise
                logger.info("tool %s args=%s", name, json.dumps(args)[:1500])
                try:
                    result = TOOLS[name](**args)
                except Exception as e:
                    logger.exception(
                        "Tool %s raised type=%s repr=%r str=%s",
                        name,
                        type(e).__name__,
                        e,
                        e,
                    )
                    result = f"Tool {name} failed (see server logs for traceback)."
                if isinstance(result, str):
                    rl = result.lower()
                    if any(
                        x in rl[:400]
                        for x in (
                            "failed",
                            "error",
                            "supadata",
                            "transcript error",
                            "not set",
                            "lookup failed",
                        )
                    ):
                        logged = (
                            result
                            if len(result) <= _MAX_TOOL_LOG_CHARS
                            else result[:_MAX_TOOL_LOG_CHARS]
                            + f"... [truncated, total {len(result)} chars]"
                        )
                        logger.error(
                            "tool %s returned error-like output (full): %s",
                            name,
                            logged,
                        )
                    else:
                        logger.info("tool %s ok, result_chars=%s", name, len(result))
                messages.append(
                    {"role": "tool", "content": result, "tool_call_id": tool_call.id}
                )
    except Exception:
        logger.exception("run() failed")
        raise


with gr.Blocks(title="AI Assistant") as demo:
    gr.Markdown("## AI Assistant - video . math . weather")
    url = gr.Textbox(
        label="Youtube URL (optional)",
        placeholder="https://www.youtube.com/watch?v=...",
    )
    qry = gr.Textbox(
        label="Question",
        placeholder="Summarise the video / 128 * 37 / Weather in Tokyo",
        lines=2,
    )
    gr.Button("Ask").click(
        fn=run, inputs=[url, qry], outputs=gr.Textbox(label="Answer", lines=10)
    )

# Vercel (and other ASGI hosts) expect a top-level ASGI `app`.
_fastapi = FastAPI()
app = gr.mount_gradio_app(_fastapi, demo, path="/")

if __name__ == "__main__":


    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "7860")),
    )
