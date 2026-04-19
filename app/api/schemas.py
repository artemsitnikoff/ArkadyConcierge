from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.version import __version__


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = __version__


class BreakdownRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Free-form task description")


class BreakdownResponse(BaseModel):
    data: dict[str, Any] = Field(
        ..., description="Parsed JSON object returned by the AI breakdown prompt",
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "data": {
                "tasks": [
                    {"system": "jira", "title": "Set up analytics", "priority": "high"},
                    {"system": "bitrix_crm", "title": "Create lead for ACME"},
                ]
            }
        }
    })
