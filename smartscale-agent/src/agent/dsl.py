from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Tuple

Point = Tuple[float, float]

class CharucoConfig(BaseModel):
    squares_x: int = 5
    squares_y: int = 7
    square_length_mm: float = 30.0
    marker_length_mm: float = 21.0
    dictionary: str = "DICT_4X4_50"

class MeasureArgs(BaseModel):
    kind: Literal["line", "angle", "circle", "polygon"] = "line"
    points: List[Point] = []  # interpretation depends on kind

class MeasureOptions(BaseModel):
    mode: Literal["auto", "fiducial", "reference"] = "auto"
    charuco: CharucoConfig = CharucoConfig()
    reference_mm: Optional[float] = None
    ref_points: List[Point] = []  # for reference length: two points
    measure: Optional[MeasureArgs] = None
    pro_accuracy_only: bool = False

class MeasureResult(BaseModel):
    ok: bool
    value_mm: Optional[float] = None
    units: str = "mm"
    px_per_mm: Optional[float] = None
    ci95_mm: Optional[float] = None
    confidence: Optional[float] = None
    method: str = ""
    message: Optional[str] = None
    provenance: dict = Field(default_factory=dict)

class MeasureRequest(BaseModel):
    options: MeasureOptions
