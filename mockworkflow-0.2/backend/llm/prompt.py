"""LLM Prompt templates for field analysis."""

from backend.schemas.field import SampleProfile, ColumnProfile


def build_field_analysis_prompt(
    profile: SampleProfile,
    target_columns: list[str] | None = None,
    rag_rules: list[dict] | None = None,
    rag_samples: list[dict] | None = None,
) -> str:
    """Build prompt for LLM to analyze sample columns.

    Args:
        profile: Sample profile with column information
        target_columns: Optional list of column names to analyze. If omitted, analyze all columns.
        rag_rules: Retrieved similar rules from vector store (RAG context)
        rag_samples: Retrieved similar sample profiles from vector store (RAG context)

    Returns:
        Formatted prompt string
    """
    from backend.rules.semantics import SemanticRegistry

    columns = target_columns or profile.columns
    semantic_names = ", ".join(SemanticRegistry.get().names)
    lines = [
        "You are a database schema expert. Analyze the following columns from a sample data file.",
        "",
        "For each column, determine:",
        "1. SQL type: one of [VARCHAR, INT, DECIMAL, DATETIME, TEXT, BOOLEAN]",
        "2. Length: for VARCHAR, suggest appropriate length (e.g., 50, 100, 255)",
        "3. Precision and Scale: for DECIMAL, suggest precision and scale (e.g., 10, 2)",
        "4. Nullable: true if column can be null, false if required",
        f"5. Semantic: one of [{semantic_names}]",
        "   - 'id' for primary keys / serial numbers",
        "   - 'time' for dates, timestamps",
        "   - 'coordinate' for lat/lng",
        "   - 'status' for status/type/category codes",
        "   - 'flag' for boolean flags",
        "   - 'text' for free text / names / descriptions",
        "   - 'license_plate' for vehicle plates",
        "   - 'company_name' for organisations / enterprises",
        "   - 'vehicle_model' for car models",
        "   - 'direction' for bearing/heading",
        "   - 'phone_number' for telephone / mobile",
        "   - 'email' for email addresses",
        "   - 'url' for web links",
        "   - 'region' for cities / districts / provinces",
        "   - 'person_name' for individual names",
        "   - 'address' for street / location addresses",
        "   - 'unknown' when none of the above fit",
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

    # -- RAG context injection --
    if rag_rules:
        lines.extend([
            "",
            "SIMILAR RULES FROM HISTORY (use as reference):",
        ])
        for i, rule in enumerate(rag_rules[:5], 1):
            meta = rule.get("metadata", {})
            lines.append(f"{i}. {rule.get('document', '')}")
            lines.append(f"   (semantic={meta.get('semantic')}, confidence={meta.get('confidence')})")

    if rag_samples:
        lines.extend([
            "",
            "SIMILAR SAMPLE PROFILES FROM HISTORY (use as reference):",
        ])
        for i, sample in enumerate(rag_samples[:3], 1):
            meta = sample.get("metadata", {})
            lines.append(f"{i}. {sample.get('document', '')}")
            lines.append(f"   (file={meta.get('file_path')}, rows={meta.get('row_count')})")

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
        f'      "semantic": "{"|".join(SemanticRegistry.get().names)}",',
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
