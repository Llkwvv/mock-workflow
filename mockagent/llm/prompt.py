"""LLM Prompt templates for field analysis."""

from mockagent.schemas.field import SampleProfile, ColumnProfile


def build_field_analysis_prompt(
    profile: SampleProfile,
    target_columns: list[str] | None = None,
) -> str:
    """Build prompt for LLM to analyze sample columns.

    Args:
        profile: Sample profile with column information
        target_columns: Optional list of column names to analyze. If omitted, analyze all columns.

    Returns:
        Formatted prompt string
    """
    columns = target_columns or profile.columns
    lines = [
        "You are a database schema expert. Analyze the following columns from a sample data file.",
        "",
        "For each column, determine:",
        "1. SQL type: one of [VARCHAR, INT, DECIMAL, DATETIME, TEXT, BOOLEAN]",
        "2. Length: for VARCHAR, suggest appropriate length (e.g., 50, 100, 255)",
        "3. Precision and Scale: for DECIMAL, suggest precision and scale (e.g., 10, 2)",
        "4. Nullable: true if column can be null, false if required",
        "5. Semantic: one of [id, time, coordinate, status, flag, text, license_plate, company_name, vehicle_model, direction, phone_number, email, url, unknown]",
        "6. Enum values: array of possible enum values if this looks like a status/type or limited-category field",
        "7. Confidence: 0.0-1.0 indicating your confidence",
        "",
        "COLUMNS TO ANALYZE:",
    ]

    for col in columns:
        profile_info = profile.column_profiles.get(col)
        samples = profile.samples.get(col, [])[:5]  # Top 5 samples

        lines.append(f"\nColumn: {col}")
        if profile_info:
            lines.append(f"  - Inferred type from data: {profile_info.inferred_type}")
            lines.append(f"  - Null ratio: {profile_info.null_ratio:.2%}")
            lines.append(f"  - Unique ratio: {profile_info.unique_ratio:.2%}")
            if profile_info.min_value is not None:
                lines.append(f"  - Min value: {profile_info.min_value}")
            if profile_info.max_value is not None:
                lines.append(f"  - Max value: {profile_info.max_value}")
        lines.append(f"  - Sample values: {samples}")

    lines.extend([
        "",
        "Return ONLY a valid JSON object with this structure:",
        "{",
        '  "fields": [',
        "    {",
        '      "name": "column_name",',
        '      "type": "VARCHAR|INT|DECIMAL|DATETIME|TEXT|BOOLEAN",',
        '      "length": 255,',
        '      "precision": 10,',
        '      "scale": 2,',
        '      "nullable": true|false,',
        '      "semantic": "id|time|coordinate|status|flag|text|license_plate|company_name|vehicle_model|direction|phone_number|email|url|unknown",',
        '      "enum_values": ["value1", "value2"],',
        '      "confidence": 0.85',
        "    }",
        "  ]",
        "}",
        "",
        "Rules:",
        "- Use DECIMAL for monetary amounts, prices, coordinates",
        "- Use VARCHAR for phone numbers, IDs, codes, license plates (not INT)",
        "- Use DATETIME for any date/time fields",
        "- Use INT for sequential IDs, counts, quantities",
        "- Set nullable=false for columns that look like required identifiers",
        "- Provide enum_values only for obvious status/type fields with limited distinct values",
    ])

    return "\n".join(lines)


def build_uncertain_field_prompt(profile: SampleProfile, uncertain_columns: list[str]) -> str:
    """Backward-compatible wrapper for uncertain field prompts."""
    return build_field_analysis_prompt(profile, uncertain_columns)
