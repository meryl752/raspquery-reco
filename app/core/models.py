from typing import Literal

from pydantic import BaseModel, Field

AppLocale = Literal["en", "fr"]
TeamSize = Literal["solo", "small", "medium", "large"]
Budget = Literal["zero", "low", "medium", "high"]
TechLevel = Literal["beginner", "intermediate", "advanced"]
Timeline = Literal["asap", "weeks", "months"]
PreferredModel = Literal["qwen-235b", "gpt-120b", "qwen-32b", "llama-70b"]
RetrievalMode = Literal["vector", "fallback"]


class UserContext(BaseModel):
    objective: str
    sector: str
    team_size: TeamSize = "solo"
    budget: Budget
    tech_level: TechLevel
    timeline: Timeline = "weeks"
    current_tools: list[str] = Field(default_factory=list)
    preferred_model: PreferredModel | None = None
    locale: AppLocale = "en"


# Modèle d'analyse strict → app.domain.analyzed_query
from app.domain.analyzed_query import AnalyzedQuery, AtomicSubtask, FunctionalDomain  # noqa: F401

class VectorAgent(BaseModel):
    id: str
    name: str
    category: str
    description: str
    price_from: float = 0
    score: float = 0
    roi_score: float = 0
    use_cases: list[str] = Field(default_factory=list)
    compatible_with: list[str] = Field(default_factory=list)
    best_for: list[str] | None = None
    not_for: list[str] | None = None
    integrations: list[str] | None = None
    website_domain: str | None = None
    logo_url: str | None = None
    website_url: str | None = None
    setup_difficulty: str | None = None
    time_to_value: str | None = None
    similarity: float = 0


class ScoredAgent(BaseModel):
    id: str
    name: str
    category: str
    description: str
    price_from: float
    score: float
    roi_score: float
    use_cases: list[str]
    compatible_with: list[str]
    similarity: float
    relevance_score: int
    relevance_reason: str
    best_for: list[str] | None = None
    integrations: list[str] | None = None
    website_domain: str | None = None
    setup_difficulty: str | None = None
    time_to_value: str | None = None


class SubTask(BaseModel):
    name: str
    without_ai: str
    with_ai: str
    tool_name: str


class StackAgent(BaseModel):
    id: str
    name: str
    category: str
    price_from: float
    score: float
    rank: int
    role: str
    reason: str
    concrete_result: str
    prompt_to_use: str | None = None
    website_domain: str | None = None
    logo_url: str | None = None
    url: str | None = None
    setup_difficulty: str | None = None
    time_to_value: str | None = None


class FinalStack(BaseModel):
    stack_name: str
    justification: str
    total_cost: float
    roi_estimate: float
    time_saved_per_week: float
    quick_wins: list[str]
    warnings: list[str]
    subtasks: list[SubTask]
    agents: list[StackAgent]


class OrchestratorMeta(BaseModel):
    agents_analyzed: int
    agents_shortlisted: int
    subtasks_detected: int
    processing_time_ms: int
    retrieval_mode: RetrievalMode
    embedding_provider: Literal["jina"] = "jina"
    embedding_latency_ms: int


class OrchestratorResult(BaseModel):
    stack: FinalStack
    meta: OrchestratorMeta
