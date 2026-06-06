from typing import Literal

from pydantic import BaseModel, Field

from app.core.models import OrchestratorResult, UserContext

PreferredModel = Literal["qwen-235b", "gpt-120b", "qwen-32b", "llama-70b"]


class RecommendRequest(BaseModel):
    """Contrat aligné sur stackai/lib/validators/api.ts → recommendSchema."""

    objective: str = Field(..., min_length=10, max_length=2000)
    sector: str = Field(..., min_length=1, max_length=100)
    budget: Literal["zero", "low", "medium", "high"]
    tech_level: Literal["beginner", "intermediate", "advanced"]
    team_size: Literal["solo", "small", "medium", "large"] = "solo"
    timeline: Literal["asap", "weeks", "months"] = "weeks"
    current_tools: list[str] = Field(default_factory=list, max_length=20)
    session_id: str | None = None
    preferred_model: PreferredModel | None = None
    regenerate: bool = False
    locale: Literal["en", "fr"] = "en"

    def to_user_context(self) -> UserContext:
        return UserContext(
            objective=self.objective.strip(),
            sector=self.sector.strip(),
            team_size=self.team_size,
            budget=self.budget,
            tech_level=self.tech_level,
            timeline=self.timeline,
            current_tools=self.current_tools or [],
            preferred_model=self.preferred_model,
            locale=self.locale,
        )


class RecommendResponse(OrchestratorResult):
    pass


class ErrorResponse(BaseModel):
    error: str
    details: list[dict[str, str]] | None = None
