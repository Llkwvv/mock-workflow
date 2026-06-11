"""Agent tool: explain generated data results to users."""

from __future__ import annotations

from typing import Any


SYSTEM_PROMPT = """你是一个Mockworkflow助手，负责用中文向用户解释生成的模拟数据结果。
你需要简明扼要地说明：
1. 生成了多少行数据
2. 数据分布特征（如数值范围、类别分布等）
3. 是否应用了特殊策略（趋势模拟、分布拟合、脱敏等）
4. 约束满足情况
"""


def explain_result(result: dict[str, Any]) -> str:
    """Generate a human-readable explanation of a generation result."""
    rows = result.get("generated_rows", 0)
    fields = result.get("fields", [])
    validation = result.get("validation", {})
    distribution = result.get("distribution_check", {})

    lines = [f"本次共生成 {rows} 行模拟数据。"]

    if fields:
        lines.append(f"涉及 {len(fields)} 个字段：{', '.join(f.get('name', '?') for f in fields[:5])}{'...' if len(fields) > 5 else ''}。")

    dist_score = distribution.get("overall_fit_score")
    if dist_score is not None:
        lines.append(f"分布拟合评分：{dist_score}（越高表示生成数据与样本分布越接近）。")

    if validation:
        status = validation.get("status", "unknown")
        failed = validation.get("failed_count", 0)
        if status == "passed":
            lines.append("数据自检通过，所有约束均满足。")
        elif status == "warning":
            lines.append(f"数据自检发现 {failed} 处警告，建议复查。")
        else:
            lines.append(f"数据自检发现 {failed} 处失败，可能需要调整生成参数。")

    return "\n".join(lines)
