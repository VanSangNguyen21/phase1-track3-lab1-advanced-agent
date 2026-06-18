from __future__ import annotations
from typing import Literal, Optional, TypedDict
from pydantic import BaseModel, Field

class ContextChunk(BaseModel):
    title: str
    text: str

class QAExample(BaseModel):
    qid: str
    difficulty: Literal["easy", "medium", "hard"]
    question: str
    gold_answer: str
    context: list[ContextChunk]

class JudgeResult(BaseModel):
    score: int = Field(..., description="Evaluation score (1 for correct, 0 for incorrect)")
    reason: str = Field(..., description="Detailed explanation of the evaluation result")
    missing_evidence: list[str] = Field(default_factory=list, description="Evidence that was missing from the answer")
    spurious_claims: list[str] = Field(default_factory=list, description="Incorrect or hallucinated facts in the answer")

class ReflectionEntry(BaseModel):
    attempt_id: int = Field(..., description="The ID of the attempt being reflected upon")
    failure_reason: str = Field(..., description="The reason why this attempt failed")
    lesson: str = Field(..., description="The lesson learned from the failure")
    next_strategy: str = Field(..., description="The proposed plan or strategy for the next attempt")

class AttemptTrace(BaseModel):
    attempt_id: int
    answer: str
    score: int
    reason: str
    reflection: Optional[ReflectionEntry] = None
    token_estimate: int = 0
    latency_ms: int = 0

class RunRecord(BaseModel):
    qid: str
    question: str
    gold_answer: str
    agent_type: Literal["react", "reflexion", "reflexion_adaptive"]
    predicted_answer: str
    is_correct: bool
    attempts: int
    token_estimate: int
    latency_ms: int
    failure_mode: Literal["none", "entity_drift", "incomplete_multi_hop", "wrong_final_answer", "looping", "reflection_overfit"]
    reflections: list[ReflectionEntry] = Field(default_factory=list)
    traces: list[AttemptTrace] = Field(default_factory=list)

class ReportPayload(BaseModel):
    meta: dict
    summary: dict
    failure_modes: dict
    examples: list[dict]
    extensions: list[str]
    discussion: str

class ReflexionState(TypedDict):
    question: str
    context: list[str]
    trajectory: list[str]
    reflection_memory: list[str]
    attempt_count: int
    success: bool
    final_answer: str
