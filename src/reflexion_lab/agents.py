from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from .mock_runtime import (
    FAILURE_MODE_BY_QID, 
    actor_answer, 
    evaluator, 
    reflector, 
    reset_metrics, 
    get_last_metrics
)
from .schemas import AttemptTrace, QAExample, ReflectionEntry, RunRecord

@dataclass
class BaseAgent:
    agent_type: Literal["react", "reflexion", "reflexion_adaptive"]
    max_attempts: int = 1
    
    def run(self, example: QAExample) -> RunRecord:
        reflection_memory: list[str] = []
        reflections: list[ReflectionEntry] = []
        traces: list[AttemptTrace] = []
        final_answer = ""
        final_score = 0
        
        # Extension: Adaptive max attempts based on difficulty
        max_attempts = self.max_attempts
        if self.agent_type == "reflexion_adaptive":
            if example.difficulty == "easy":
                max_attempts = min(max_attempts, 2)
            elif example.difficulty == "hard":
                max_attempts = max(max_attempts, 4)

        for attempt_id in range(1, max_attempts + 1):
            # 1. Reset metrics & run Actor
            reset_metrics()
            answer = actor_answer(example, attempt_id, self.agent_type, reflection_memory)
            actor_tokens, actor_latency = get_last_metrics()
            
            # 2. Reset metrics & run Evaluator
            reset_metrics()
            judge = evaluator(example, answer)
            evaluator_tokens, evaluator_latency = get_last_metrics()
            
            reflector_tokens = 0
            reflector_latency = 0
            reflection_entry = None
            
            # 3. Check if we should perform Reflection (only for reflexion and reflexion_adaptive)
            is_reflexion = self.agent_type in ["reflexion", "reflexion_adaptive"]
            if judge.score != 1 and is_reflexion and attempt_id < max_attempts:
                # Reset metrics & run Reflector
                reset_metrics()
                reflection_entry = reflector(example, attempt_id, judge, answer=answer)
                reflector_tokens, reflector_latency = get_last_metrics()
                reflections.append(reflection_entry)
                # Save next strategy to memory
                reflection_memory.append(
                    f"Attempt {attempt_id} failed. Reason: {reflection_entry.failure_reason}. "
                    f"Lesson: {reflection_entry.lesson}. Strategy: {reflection_entry.next_strategy}"
                )

            # Calculate actual tokens and latency for this attempt (actor + evaluator + reflector)
            token_estimate = actor_tokens + evaluator_tokens + reflector_tokens
            latency_ms = actor_latency + evaluator_latency + reflector_latency
            
            trace = AttemptTrace(
                attempt_id=attempt_id, 
                answer=answer, 
                score=judge.score, 
                reason=judge.reason, 
                reflection=reflection_entry,
                token_estimate=token_estimate, 
                latency_ms=latency_ms
            )
            final_answer = answer
            final_score = judge.score
            traces.append(trace)
            
            if judge.score == 1:
                break
                
        total_tokens = sum(t.token_estimate for t in traces)
        total_latency = sum(t.latency_ms for t in traces)
        failure_mode = "none" if final_score == 1 else FAILURE_MODE_BY_QID.get(example.qid, "wrong_final_answer")
        
        return RunRecord(
            qid=example.qid, 
            question=example.question, 
            gold_answer=example.gold_answer, 
            agent_type=self.agent_type, 
            predicted_answer=final_answer, 
            is_correct=bool(final_score), 
            attempts=len(traces), 
            token_estimate=total_tokens, 
            latency_ms=total_latency, 
            failure_mode=failure_mode, 
            reflections=reflections, 
            traces=traces
        )

class ReActAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(agent_type="react", max_attempts=1)

class ReflexionAgent(BaseAgent):
    def __init__(self, max_attempts: int = 3) -> None:
        super().__init__(agent_type="reflexion", max_attempts=max_attempts)

class ReflexionAdaptiveAgent(BaseAgent):
    def __init__(self, max_attempts: int = 3) -> None:
        super().__init__(agent_type="reflexion_adaptive", max_attempts=max_attempts)
