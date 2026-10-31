from enum import Enum
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

class Op(str, Enum):
    count_rows = "count_rows"
    aggregate = "aggregate"
    top_n = "top_n"
    value_counts = "value_counts"
    describe = "describe"
    correlation = "correlation"
    forecast = "forecast"          # ML: linear regression trend
    anomalies = "anomalies"        # ML: Isolation Forest
    clusters = "clusters"          # ML: KMeans

class Filter(BaseModel):
    column: str
    op: Literal["==", "!=", ">", "<", ">=", "<=", "contains"]
    value: Any

class AnalysisPlan(BaseModel):
    operation: Op
    column: Optional[str] = None
    agg: Literal["sum", "mean", "min", "max", "median"] = "mean"
    group_by: Optional[str] = None
    filters: list[Filter] = []
    n: int = Field(5, ge=1, le=50)
    k: int = Field(3, ge=2, le=8)
    target: Optional[str] = None
    ascending: bool = False

class AnalysisResult(BaseModel):
    operation: Op
    title: str
    columns: list[str]
    rows: list[list[Any]]
    chart: Optional[dict] = None
    facts: dict = {}
    numbers: list[float] = []

class AnalysisError(Exception):
    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.message, self.code = message, code
