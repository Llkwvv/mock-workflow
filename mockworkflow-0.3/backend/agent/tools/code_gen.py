"""Agent tool: auto-generate custom field generators with sandboxed execution."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import os
import re
import textwrap
from pathlib import Path
from typing import Any

from backend.config import Settings
from backend.llm.client import get_client


CUSTOM_DIR = Path(__file__).resolve().parent.parent.parent.parent / "custom"

# AST node types permitted in custom generator code
_SAFE_AST_NODES: set[type] = {
    ast.Module, ast.FunctionDef, ast.arguments, ast.arg,
    ast.Return, ast.Expr, ast.Pass, ast.Break, ast.Continue,
    ast.Assign, ast.AugAssign, ast.NamedExpr,
    ast.If, ast.For, ast.While,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
    ast.IfExp,
    ast.Name, ast.Constant, ast.Attribute, ast.Subscript,
    ast.List, ast.Tuple, ast.Set, ast.Dict,
    ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp, ast.comprehension,
    ast.Call, ast.keyword,
    ast.FormattedValue, ast.JoinedStr,
    ast.Index, ast.Slice, ast.ExtSlice, ast.Load, ast.Store, ast.Del,
    ast.Import, ast.ImportFrom, ast.alias,
}

# Names that must NOT appear as call targets
_DISALLOWED_CALLS: set[str] = {
    "open", "eval", "exec", "compile", "__import__",
    "os.system", "subprocess.call", "subprocess.run", "subprocess.Popen",
    "input", "print",
    "dir", "globals", "locals", "vars",
}

# Allowed top-level imports
_SAFE_IMPORTS: set[str] = {
    "random", "datetime", "timedelta", "date", "Decimal",
    "math", "statistics", "string", "itertools", "functools",
    "fractions", "decimal",
}


def _validate_custom_code(source: str, filename: str = "<generated>") -> None:
    """Validate generated code via AST before saving or executing."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        raise ValueError(f"Invalid Python syntax: {exc}") from exc

    for node in ast.walk(tree):
        # Block class definitions early with a friendly message
        if isinstance(node, ast.ClassDef):
            raise ValueError("Class definitions are not allowed")

        # Block lambda early
        if isinstance(node, ast.Lambda):
            raise ValueError("Lambda expressions are not allowed")

        # Allow only safe imports (checked before generic whitelist)
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in _SAFE_IMPORTS:
                    raise ValueError(f"Disallowed import: {alias.name}")
        if isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in _SAFE_IMPORTS:
                raise ValueError(f"Disallowed import from: {node.module}")

        # Generic AST node whitelist
        if type(node) not in _SAFE_AST_NODES:
            raise ValueError(f"Disallowed AST node: {type(node).__name__}")

        # Block dangerous calls
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _DISALLOWED_CALLS:
                raise ValueError(f"Disallowed call: {node.func.id}")
            if isinstance(node.func, ast.Attribute) and node.func.attr in _DISALLOWED_CALLS:
                raise ValueError(f"Disallowed call: {node.func.attr}")


def generate_custom_field_code(
    description: str,
    field_name: str,
    settings: Settings,
) -> str:
    """Use LLM to generate a Python function that produces values for a custom field.

    The generated function must be named ``generate_{field_name}`` and accept ``index: int``.
    It should return a single value (str, int, float, etc.).
    """
    if not settings.llm_enabled:
        raise ValueError("LLM must be enabled to generate custom field code")

    client = get_client(settings)
    safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", field_name)
    prompt = (
        f"Write a Python function that generates realistic values for a database column.\n"
        f"Column name: {field_name}\n"
        f"Description: {description}\n\n"
        f"Requirements:\n"
        f"- Function name must be: generate_{safe_name}\n"
        f"- Signature: def generate_{safe_name}(index: int) -> object:\n"
        f"- The function should use only Python standard library (random, datetime, etc.).\n"
        f"- Do not write any import statements inside the function (assume imports at top).\n"
        f"- Return a single value, no print statements, no side effects.\n"
        f"- Wrap the function in a markdown code block.\n"
    )

    response = client.chat.completions.create(
        model=settings.llm_model or "gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You generate safe Python functions for mock data."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=800,
        temperature=0.2,
    )
    content = response.choices[0].message.content or ""
    # Extract code block
    match = re.search(r"```python\n(.*?)\n```", content, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: return raw if it looks like a def
    if "def " in content:
        return content.strip()
    raise ValueError("LLM did not return a valid Python function")


def install_custom_generator(
    field_name: str,
    code: str,
    custom_dir: Path | None = None,
) -> Path:
    """Save generated code to custom/ directory with a hash-based filename."""
    _validate_custom_code(code, filename="<generated>")
    directory = custom_dir or CUSTOM_DIR
    directory.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", field_name)
    code_hash = hashlib.md5(code.encode("utf-8")).hexdigest()[:8]
    filename = f"gen_{safe_name}_{code_hash}.py"
    filepath = directory / filename

    module_code = textwrap.dedent(
        f"""\
        # Auto-generated custom field generator for {field_name}
        import random
        from datetime import datetime, timedelta, date
        from decimal import Decimal

        {code}
        """
    )
    filepath.write_text(module_code, encoding="utf-8")
    return filepath


def load_custom_generators(custom_dir: Path | None = None) -> dict[str, callable]:
    """Load all custom generators from the custom/ directory."""
    directory = custom_dir or CUSTOM_DIR
    generators: dict[str, callable] = {}
    if not directory.exists():
        return generators

    for filepath in directory.glob("gen_*.py"):
        try:
            # Read source and exec in a restricted namespace
            source = filepath.read_text(encoding="utf-8")
            _validate_custom_code(source, filename=str(filepath))
            namespace: dict[str, Any] = {
                "__builtins__": {
                    "len": len, "range": range, "str": str, "int": int, "float": float,
                    "bool": bool, "list": list, "dict": dict, "set": set, "tuple": tuple,
                    "abs": abs, "min": min, "max": max, "sum": sum, "round": round,
                    "zip": zip, "map": map, "filter": filter, "enumerate": enumerate,
                    "isinstance": isinstance, "hasattr": hasattr, "getattr": getattr,
                    "ValueError": ValueError, "TypeError": TypeError, "Exception": Exception,
                },
            }
            exec(compile(source, str(filepath), "exec"), namespace)
            # Find functions matching generate_*
            for name, obj in namespace.items():
                if callable(obj) and name.startswith("generate_"):
                    generators[name] = obj
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Failed to load %s: %s", filepath, e)

    return generators
