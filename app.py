import os, json, dotenv
import gradio as gr
from openai import OpenAI
from mcp_server import get_transcript, calculate, get_weather


dotenv.load_dotenv()

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
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL")
    if not api_key or not base_url:
        raise ValueError("OPENROUTER_API_KEY is not set")
    client = OpenAI(api_key=api_key, base_url=base_url)

    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant. When a tool returns a result, always use that result to answer. Only call get_transcript if the user asks for the transcript of a Youtube video.",
        },
        {"role": "user", "content": (f"URL: {url}\n\n" if url.strip() else "") + query},
    ]

    while True:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=messages,
            tools=SCHEMAS,
            tool_choice="auto",
        )
        message = response.choices[0].message
        if not message.tool_calls:
            return message.content

        messages.append(message)

        for tool_call in message.tool_calls:
            result = TOOLS[tool_call.function.name](
                **json.loads(tool_call.function.arguments)
            )
            messages.append(
                {"role": "tool", "content": result, "tool_call_id": tool_call.id}
            )


with gr.Blocks(title="AI Assistant") as app:
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

app.launch(server_name="0.0.0.0", server_port=int(os.getenv("PORT", 7860)))
