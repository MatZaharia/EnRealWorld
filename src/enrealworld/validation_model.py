"""Strict validation primitives shared by graph and numeric inspection tools."""
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field
Scalar = Annotated[float, Field(allow_inf_nan=False)]
Positive = Annotated[Scalar, Field(gt=0)]
NonNegative = Annotated[Scalar, Field(ge=0)]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")]

class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, allow_inf_nan=False)
