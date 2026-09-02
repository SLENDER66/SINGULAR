from __future__ import annotations
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict

class Certainty(str, Enum):
    FACT='FACT'; HYPOTHESIS='HYPOTHESIS'; ESTIMATE='ESTIMATE'; OBJECTIVE='OBJECTIVE'; ASPIRATION='ASPIRATION'; UNKNOWN='UNKNOWN'

class Status(str, Enum):
    ACTIVE='ACTIVE'; PLANNED='PLANNED'; BLOCKED='BLOCKED'; DONE='DONE'; CANCELLED='CANCELLED'; PROPOSED='PROPOSED'

class Evidence(BaseModel):
    id: str
    statement: str
    certainty: Certainty
    source: Optional[str] = None
    confidence: float = Field(ge=0, le=1, default=0.8)

class Objective(BaseModel):
    id: str
    name: str
    pillar: str
    importance: float = Field(ge=0, le=10)
    target: str
    status: Status = Status.ACTIVE
    progress: float = Field(ge=0, le=1, default=0)
    deadline: Optional[str] = None

class Resource(BaseModel):
    name: str
    kind: str
    available: float
    unit: str

class Opportunity(BaseModel):
    id: str
    name: str
    impact: float = Field(ge=0, le=10)
    probability: float = Field(ge=0, le=1)
    leverage: float = Field(ge=0, le=10)
    cost: float = Field(ge=0, le=10)
    risk: float = Field(ge=0, le=10)
    reversibility: float = Field(ge=0, le=10)
    optionality: float = Field(ge=0, le=10, default=5)
    status: str = 'WATCH'

class Risk(BaseModel):
    id: str
    name: str
    probability: float = Field(ge=0, le=1)
    impact: float = Field(ge=0, le=10)
    reversibility: float = Field(ge=0, le=10)
    mitigation: Optional[str] = None

class Action(BaseModel):
    id: str
    name: str
    impact: float = Field(ge=0, le=10)
    urgency: float = Field(ge=0, le=10)
    leverage: float = Field(ge=0, le=10)
    effort: float = Field(gt=0, le=10)
    risk: float = Field(ge=0, le=10)
    reversibility: float = Field(ge=0, le=10)
    optionality: float = Field(ge=0, le=10, default=5)
    objective_id: Optional[str] = None

class Decision(BaseModel):
    id: str
    question: str
    context: str = ''
    facts: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)
    recommendation: str = ''
    confidence: float = Field(ge=0, le=1, default=0.5)
    red_team: list[str] = Field(default_factory=list)
    reversal_plan: Optional[str] = None
    validation_required: bool = False
    status: Status = Status.PROPOSED
    expected_result: Optional[str] = None
    actual_result: Optional[str] = None
    lesson: Optional[str] = None

class Learning(BaseModel):
    id: str
    hypothesis: str
    prediction: str
    result: str
    lesson: str
    confidence: float = Field(ge=0, le=1, default=0.5)

class WorldModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: str = '1.0'
    updated_at: Optional[str] = None
    mission: str = 'Maximiser le progrès réel sous contraintes.'
    objectives: list[Objective] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    resources: list[Resource] = Field(default_factory=list)
    opportunities: list[Opportunity] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    learnings: list[Learning] = Field(default_factory=list)
