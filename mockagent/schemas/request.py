from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    sample_file: str = Field(min_length=1)
    rows: int = Field(default=100, gt=0)
    table_name: str = Field(default="auto_table", min_length=1)
    output: str = Field(default="preview")
    csv_path: str | None = None
