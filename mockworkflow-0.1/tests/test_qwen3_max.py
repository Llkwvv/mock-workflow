"""
Integration probe for an OpenAI-compatible LLM endpoint.
Model, API key and base URL are read from environment variables.
Tests: basic completion, streaming output, function calling.
"""

import json
import os

import pytest
from openai import OpenAI

API_KEY = os.environ.get("MOCKWORKFLOW_LLM_API_KEY")
BASE_URL = os.environ.get("MOCKWORKFLOW_LLM_BASE_URL")
MODEL = os.environ.get("MOCKWORKFLOW_LLM_MODEL")

pytestmark = pytest.mark.skipif(
    not API_KEY or not BASE_URL or not MODEL,
    reason="Set MOCKWORKFLOW_LLM_API_KEY, MOCKWORKFLOW_LLM_BASE_URL and MOCKWORKFLOW_LLM_MODEL to run this integration probe.",
)

client = (
    OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=60)
    if API_KEY and BASE_URL
    else None
)


def test_basic_completion():
    """Test 1: Basic (non-streaming) chat completion."""
    print("=" * 60)
    print("TEST 1: Basic Completion")
    print("=" * 60)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Reply concisely."},
            {"role": "user", "content": "用一句话介绍杭州"},
        ],
        max_tokens=200,
        temperature=0.7,
    )

    print(f"Response type : {type(response).__name__}")
    print(f"Model         : {response.model}")
    print(f"ID            : {response.id}")
    print(f"Usage         : {response.usage}")
    print(f"Finish reason : {response.choices[0].finish_reason}")
    print(f"Content       : {response.choices[0].message.content}")
    print(f"\nFull message object keys: {vars(response.choices[0].message).keys()}")
    print(f"Full message dump:\n{response.choices[0].message.model_dump_json(indent=2)}")
    print()


def test_streaming():
    """Test 2: Streaming output — inspect each chunk's structure."""
    print("=" * 60)
    print("TEST 2: Streaming Output")
    print("=" * 60)

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Reply concisely."},
            {"role": "user", "content": "列出 Python 的 3 个优点，每个一句话"},
        ],
        max_tokens=300,
        temperature=0.7,
        stream=True,
    )

    print("--- Chunk inspection (first 5 chunks) ---")
    collected_content = ""
    for i, chunk in enumerate(stream):
        if i < 5:
            print(f"\nChunk {i}:")
            print(f"  type        : {type(chunk).__name__}")
            print(f"  id          : {chunk.id}")
            print(f"  model       : {chunk.model}")
            print(f"  choices len : {len(chunk.choices)}")
            if chunk.choices:
                delta = chunk.choices[0].delta
                print(f"  delta keys  : {vars(delta).keys()}")
                print(f"  delta dump  : {delta.model_dump_json()}")
                print(f"  finish_reason: {chunk.choices[0].finish_reason}")

        # Accumulate content
        if chunk.choices and chunk.choices[0].delta.content:
            collected_content += chunk.choices[0].delta.content

    print("\n--- Full streamed content ---")
    print(collected_content)
    print()


def test_function_calling():
    """Test 3: Function calling — inspect tool_calls structure."""
    print("=" * 60)
    print("TEST 3: Function Calling")
    print("=" * 60)

    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather for a given city",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "City name, e.g. 杭州",
                        },
                        "unit": {
                            "type": "string",
                            "enum": ["celsius", "fahrenheit"],
                            "description": "Temperature unit",
                        },
                    },
                    "required": ["city"],
                },
            },
        }
    ]

    # --- 3a: Non-streaming function call ---
    print("\n--- 3a: Non-streaming function call ---")
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "杭州今天天气怎么样？"},
        ],
        tools=tools,
        tool_choice="auto",
        max_tokens=300,
        temperature=0.7,
    )

    msg = response.choices[0].message
    print(f"Finish reason : {response.choices[0].finish_reason}")
    print(f"Message role  : {msg.role}")
    print(f"Content       : {msg.content}")
    print(f"Tool calls    : {msg.tool_calls}")
    print(f"\nFull message dump:\n{msg.model_dump_json(indent=2)}")

    if msg.tool_calls:
        for tc in msg.tool_calls:
            print(f"\n  tool_call id       : {tc.id}")
            print(f"  tool_call type     : {tc.type}")
            print(f"  function name      : {tc.function.name}")
            print(f"  function arguments : {tc.function.arguments}")
            print(f"  arguments type     : {type(tc.function.arguments).__name__}")

    # --- 3b: Streaming function call ---
    print("\n--- 3b: Streaming function call ---")
    stream = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "帮我查一下北京的天气"},
        ],
        tools=tools,
        tool_choice="auto",
        max_tokens=300,
        temperature=0.7,
        stream=True,
    )

    print("--- Streaming chunks with tool_calls ---")
    all_chunks = []
    for i, chunk in enumerate(stream):
        all_chunks.append(chunk)
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and (delta.tool_calls or delta.content):
            print(f"\nChunk {i}:")
            print(f"  delta dump  : {delta.model_dump_json()}")
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    print(f"  tool_call delta: index={tc_delta.index}, "
                          f"id={tc_delta.id}, type={tc_delta.type}")
                    if tc_delta.function:
                        print(f"    function.name={tc_delta.function.name}, "
                              f"function.arguments={tc_delta.function.arguments}")
        if chunk.choices and chunk.choices[0].finish_reason:
            print(f"\nFinal chunk {i}: finish_reason={chunk.choices[0].finish_reason}")

    print()


if __name__ == "__main__":
    test_basic_completion()
    test_streaming()
    test_function_calling()
    print("All tests completed!")
