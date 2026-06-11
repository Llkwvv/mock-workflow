"""Tests for backend/agent/tools/code_gen.py AST sandbox validation."""
import pytest

from backend.agent.tools.code_gen import _validate_custom_code


def test_valid_simple_function():
    code = """
def generate_custom(index: int) -> str:
    return f"value_{index}"
"""
    _validate_custom_code(code)  # should not raise


def test_valid_with_import():
    code = """
import random

def generate_custom(index: int) -> str:
    return str(random.randint(0, 100))
"""
    _validate_custom_code(code)


def test_disallowed_open_call():
    code = """
def generate_custom(index: int) -> str:
    return open("/etc/passwd").read()
"""
    with pytest.raises(ValueError, match="Disallowed call: open"):
        _validate_custom_code(code)


def test_disallowed_eval():
    code = """
def generate_custom(index: int) -> str:
    return eval("1+1")
"""
    with pytest.raises(ValueError, match="Disallowed call: eval"):
        _validate_custom_code(code)


def test_disallowed_import_os():
    code = """
import os

def generate_custom(index: int) -> str:
    return os.system("ls")
"""
    with pytest.raises(ValueError, match="Disallowed import: os"):
        _validate_custom_code(code)


def test_disallowed_class_def():
    code = """
class Bad:
    pass

def generate_custom(index: int) -> str:
    return "ok"
"""
    with pytest.raises(ValueError, match="Class definitions"):
        _validate_custom_code(code)


def test_disallowed_lambda():
    code = """
def generate_custom(index: int) -> str:
    f = lambda x: x + 1
    return str(f(index))
"""
    with pytest.raises(ValueError, match="Lambda"):
        _validate_custom_code(code)


def test_invalid_syntax():
    code = "def generate_custom(index: int) -> str: return 1 +"
    with pytest.raises(ValueError, match="Invalid Python syntax"):
        _validate_custom_code(code)
