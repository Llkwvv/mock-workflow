"""
Test script using native DashScope SDK (dashscope.Generation).
Tests: basic completion, streaming output, function calling.
"""

import json
import os

import pytest
from dashscope import Generation

API_KEY = os.environ.get("MOCKWORKFLOW_LLM_API_KEY")
MODEL = os.environ.get("MOCKWORKFLOW_LLM_MODEL")

pytestmark = pytest.mark.skipif(
    not API_KEY or not MODEL,
    reason="Set MOCKWORKFLOW_LLM_API_KEY and MOCKWORKFLOW_LLM_MODEL to run this integration probe.",
)


def test_basic_completion():
    """Test 1: Basic (non-streaming) chat completion."""
    print("=" * 60)
    print("TEST 1: Basic Completion (native SDK)")
    print("=" * 60)

    response = Generation.call(
        api_key=API_KEY,
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Reply concisely."},
            {"role": "user", "content": "用一句话介绍杭州"},
        ],
        result_format="message",
        max_tokens=200,
        temperature=0.7,
    )

    print(f"Response type  : {type(response).__name__}")
    print(f"Status code    : {response.status_code}")

    if response.status_code == 200:
        print(f"Request ID     : {response.request_id}")
        print(f"Usage          : {response.usage}")
        choice = response.output.choices[0]
        print(f"Finish reason  : {choice.finish_reason}")
        print(f"Message role   : {choice.message.role}")
        print(f"Message content: {choice.message.content}")
        print(f"\nFull output dump: {response.output}")
    else:
        print(f"Error code     : {response.code}")
        print(f"Error message  : {response.message}")
    print()


def test_streaming():
    """Test 2: Streaming output — inspect each chunk."""
    print("=" * 60)
    print("TEST 2: Streaming Output (native SDK)")
    print("=" * 60)

    responses = Generation.call(
        api_key=API_KEY,
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Reply concisely."},
            {"role": "user", "content": "列出 Python 的 3 个优点，每个一句话"},
        ],
        result_format="message",
        max_tokens=300,
        temperature=0.7,
        stream=True,
        incremental_output=True,
    )

    print("--- Chunk inspection (first 5 chunks) ---")
    collected_content = ""
    for i, chunk in enumerate(responses):
        if i < 5:
            print(f"\nChunk {i}:")
            print(f"  type          : {type(chunk).__name__}")
            print(f"  status_code   : {chunk.status_code}")
            if chunk.status_code == 200:
                choice = chunk.output.choices[0]
                print(f"  finish_reason : {choice.finish_reason}")
                print(f"  message role  : {choice.message.role}")
                print(f"  message content: {repr(choice.message.content)}")
                print(f"  usage         : {chunk.usage}")

        if chunk.status_code == 200:
            content = chunk.output.choices[0].message.content
            if content:
                collected_content += content

    print("\n--- Full streamed content ---")
    print(collected_content)
    print()


def test_function_calling():
    """Test 3: Function calling — inspect tool_calls structure."""
    print("=" * 60)
    print("TEST 3: Function Calling (native SDK)")
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
    response = Generation.call(
        api_key=API_KEY,
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "杭州今天天气怎么样？"},
        ],
        tools=tools,
        result_format="message",
        max_tokens=300,
        temperature=0.7,
    )

    print(f"Status code   : {response.status_code}")
    if response.status_code == 200:
        choice = response.output.choices[0]
        msg = choice.message
        print(f"Finish reason : {choice.finish_reason}")
        print(f"Message role  : {msg.role}")
        print(f"Content       : {msg.content}")
        print(f"Tool calls    : {msg.get('tool_calls', None)}")
        print(f"\nFull output dump: {response.output}")

        tool_calls = msg.get("tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                print(f"\n  tool_call id       : {tc.get('id')}")
                print(f"  tool_call type     : {tc.get('type')}")
                func = tc.get("function", {})
                print(f"  function name      : {func.get('name')}")
                print(f"  function arguments : {func.get('arguments')}")
                print(f"  arguments type     : {type(func.get('arguments')).__name__}")
    else:
        print(f"Error: {response.code} - {response.message}")

    # --- 3b: Streaming function call ---
    print("\n--- 3b: Streaming function call ---")
    responses = Generation.call(
        api_key=API_KEY,
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "帮我查一下北京的天气"},
        ],
        tools=tools,
        result_format="message",
        max_tokens=300,
        temperature=0.7,
        stream=True,
        incremental_output=True,
    )

    print("--- Streaming chunks with tool_calls ---")
    for i, chunk in enumerate(responses):
        if chunk.status_code == 200:
            choice = chunk.output.choices[0]
            msg = choice.message
            tool_calls = msg.get("tool_calls", None)
            content = msg.content

            if tool_calls or content:
                print(f"\nChunk {i}:")
                print(f"  finish_reason : {choice.finish_reason}")
                if content:
                    print(f"  content       : {repr(content)}")
                if tool_calls:
                    for tc in tool_calls:
                        print(f"  tool_call     : {tc}")
            if choice.finish_reason == "tool_calls" or choice.finish_reason == "stop":
                print(f"\nFinal chunk {i}: finish_reason={choice.finish_reason}")
        else:
            print(f"Chunk {i} error: {chunk.code} - {chunk.message}")

    print()


if __name__ == "__main__":
    test_basic_completion()
    test_streaming()
    test_function_calling()
    print("All tests completed!")
