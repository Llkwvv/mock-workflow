"""Natural-language-driven sample reader code generator.

Usage:
    gen = ReaderCodeGenerator()
    code = gen.generate("rdf", "RDF/XML semantic web data", "流式解析，100MB以上降频采样")
    path = gen.install("rdf", code)
"""

import importlib.util
import logging
import re
from pathlib import Path

from openai import OpenAI

from backend.config import get_settings

logger = logging.getLogger(__name__)

# Simple static guard – anything more dangerous should be caught by code review.
_FORBIDDEN_PATTERNS = {
    "os.system",
    "subprocess",
    "eval(",
    "exec(",
    "__import__",
    "compile(",
}

_PROMPT = """You are a senior Python engineer.

Your task: generate a complete, self-contained Python module that implements a sample file reader for the mockworkflow project.

Requirements:
1. The module MUST use the decorator ``@register_reader("{suffix}")`` on a function named ``read_{suffix}``.
2. The function signature MUST be exactly:
   ``def read_{suffix}(path: Path) -> pd.DataFrame:``
3. You MAY import ``from pathlib import Path`` and ``import pandas as pd``.
4. You MAY also import ``from backend.sample.registry import register_reader``.
5. You MAY use any standard library modules suitable for the file format (e.g. ``xml.etree.ElementTree``, ``json``, ``zipfile``, etc.).
6. The function must return a ``pandas.DataFrame``.  If the source has no obvious schema, flatten nested structures into flat string columns.
7. Handle large-file concerns if the user asks for streaming / sampling – you may read a subset of rows and return them.
8. Do NOT include ``if __name__ == "__main__":``, tests, or example usage.
9. Do NOT use ``os.system``, ``subprocess``, ``eval``, ``exec``, or ``__import__``.
10. Provide ONLY the Python code inside a single markdown code block (language = python).

File suffix (extension): ``.{suffix}``
Description: {description}
{strategy_line}
{sample_snippet_line}

Generate the code now.
"""


class ReaderCodeGenerator:
    """Generate and install sample-reader plugins via LLM."""

    def __init__(self):
        settings = get_settings()
        self.api_key = settings.llm_api_key or "not-needed"
        self.base_url = settings.llm_base_url
        self.model = settings.llm_model
        self.timeout = settings.llm_timeout
        self.max_tokens = settings.llm_max_tokens
        self.temperature = settings.llm_temperature

        if not self.model:
            raise ValueError("llm_model must be configured to generate readers")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

    def generate(
        self,
        suffix: str,
        description: str,
        strategy: str | None = None,
        sample_snippet: str | None = None,
    ) -> str:
        """Ask the LLM to generate reader source code.

        Args:
            suffix: File suffix without dot, e.g. ``"rdf"``.
            description: Human-readable description of the format.
            strategy: Optional parsing strategy hints (streaming, sampling, etc.).
            sample_snippet: Optional first lines of a real sample file for LLM reference.

        Returns:
            Generated Python source code.
        """
        strategy_line = f"Strategy / constraints: {strategy}" if strategy else ""
        sample_snippet_line = (
            f"Here are the first lines of a real sample file for reference:\n---\n{sample_snippet}\n---"
            if sample_snippet else ""
        )
        prompt = _PROMPT.format(
            suffix=suffix,
            description=description,
            strategy_line=strategy_line,
            sample_snippet_line=sample_snippet_line,
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are an expert Python backend developer."},
                {"role": "user", "content": prompt},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        if response is None:
            raise ValueError("LLM returned no response")
        choices = getattr(response, "choices", None)
        if not choices:
            # 打印原始响应结构以便调试
            raw = str(getattr(response, "model_dump", lambda: repr(response))())
            raise ValueError(f"LLM returned no choices. Raw response: {raw[:800]}")
        choice = choices[0]
        message = getattr(choice, "message", None)
        if message is None:
            raw_choice = str(getattr(choice, "model_dump", lambda: repr(choice))())
            raise ValueError(f"LLM returned no message in choice. Choice dump: {raw_choice[:800]}")
        content = getattr(message, "content", None)
        if not content:
            raw_msg = str(getattr(message, "model_dump", lambda: repr(message))())
            raise ValueError(f"LLM returned empty content. Message dump: {raw_msg[:800]}")

        # Extract code block
        match = re.search(r"```python\s*(.*?)```", content, re.DOTALL)
        if match:
            code = match.group(1).strip()
        else:
            code = content.strip()

        self._validate(code)
        return code

    @staticmethod
    def _validate(code: str) -> None:
        """Static guard against obviously dangerous patterns."""
        for bad in _FORBIDDEN_PATTERNS:
            if bad in code:
                raise ValueError(f"Generated code contains forbidden pattern: {bad}")

    def install(
        self,
        suffix: str,
        code: str,
        readers_dir: Path | None = None,
    ) -> Path:
        """Save generated code and hot-load it into the running process.

        Args:
            suffix: File suffix (used for filename ``auto_<suffix>.py``).
            code: Python source generated by :meth:`generate`.
            readers_dir: Target directory.  Defaults to ``backend/sample/readers``.

        Returns:
            Path where the file was written.
        """
        if readers_dir is None:
            readers_dir = Path(__file__).resolve().parent / "readers"
        readers_dir.mkdir(parents=True, exist_ok=True)

        file_path = readers_dir / f"auto_{suffix}.py"
        file_path.write_text(code, encoding="utf-8")

        # Hot-load so the new reader is immediately available
        module_name = f"auto_{suffix}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Failed to create module spec for {file_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        logger.info("Installed auto-generated reader: %s", file_path)
        return file_path
