"""Give any OpenAI-compatible LLM a free web_search tool."""

import json

import requests
from openai import OpenAI  # pip install openai requests

FREESEARCH = "http://localhost:8000"
client = OpenAI()

tools = [{
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for up-to-date information",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
}]


def web_search(query: str) -> str:
    data = requests.get(f"{FREESEARCH}/search", params={"q": query, "max_results": 6}, timeout=20).json()
    return json.dumps([{"title": r["title"], "url": r["url"], "snippet": r["content"]} for r in data["results"]])


messages = [{"role": "user", "content": "What changed in the latest FastAPI release?"}]
reply = client.chat.completions.create(model="gpt-4o-mini", messages=messages, tools=tools)
msg = reply.choices[0].message
if msg.tool_calls:
    messages.append(msg)
    for call in msg.tool_calls:
        result = web_search(**json.loads(call.function.arguments))
        messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
    reply = client.chat.completions.create(model="gpt-4o-mini", messages=messages)
print(reply.choices[0].message.content)
