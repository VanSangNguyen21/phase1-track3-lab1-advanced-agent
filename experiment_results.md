# Experiment Results: Reflexion Agent Implementation (Lab 16)

This report details the implementation of the **Reflexion Agent** architecture, designed to self-correct reasoning mistakes via an evaluation and reflection loop.

We have successfully completed all core task components and implemented multiple advanced extensions, achieving a perfect **100/100** score on the automated grading system.

---

## 🛠️ Implementation Summary

### 1. Schema Definitions (`schemas.py`)
- Completed Pydantic schema mappings for [schemas.py](file:///C:/ai_vinuni/code_vinuni/phase1-track3-lab1-advanced-agent/src/reflexion_lab/schemas.py).
- **`JudgeResult`**: Defines score verification (0/1), semantic reasoning explanations, missing evidence list, and spurious/hallucinated claims tracker.
- **`ReflectionEntry`**: Represents a single correction attempt containing the failed attempt ID, failure reason, the lesson learned, and the next step strategy.

### 2. Main Agent Execution Flow (`agents.py`)
- Completed the Reflexion loop in [agents.py](file:///C:/ai_vinuni/code_vinuni/phase1-track3-lab1-advanced-agent/src/reflexion_lab/agents.py).
- Integrated the Actor-Evaluator-Reflector pipeline:
  1. The Actor writes the answer using the documents' context and any prior reflection memory.
  2. The Evaluator performs a structured JSON grade of the response.
  3. If incorrect, the Reflector analyzes the error and produces a strategy, appending it to the `reflection_memory` before iterating.
- Implemented **Adaptive Max Attempts**: Dynamically adjusted maximum attempts based on question difficulty (e.g., lower budget for `easy` questions, higher budget for `hard` questions).

### 3. Prompt Design (`prompts.py`)
- Developed precise, structured system instructions in [prompts.py](file:///C:/ai_vinuni/code_vinuni/phase1-track3-lab1-advanced-agent/src/reflexion_lab/prompts.py) to guarantee deterministic JSON formatting and reasoning structure from the LLM.

### 4. API & Mock Runtime Toggle (`mock_runtime.py`)
- Redesigned [mock_runtime.py](file:///C:/ai_vinuni/code_vinuni/phase1-track3-lab1-advanced-agent/src/reflexion_lab/mock_runtime.py) to run seamlessly in both mock and real LLM mode via a runtime environment toggle (`REFLEXION_MODE`).
- Equipped the client with a robust **Rate Limiter** enforcing a 3-second request pacing delay, and **Exponential Backoff Retries** (sleeping up to 120s on HTTP 429) to handle API rate limits.
- Integrated real token usage tracking and API latency parsing from response bodies to replace hardcoded metrics.

---

## 📊 Benchmark Results

### 1. Mock Mode Evaluation (100 Dev Samples)
We constructed a dataset of **100 real HotpotQA examples** saved under `data/hotpot_dev_100.json`. Running the mock evaluation on these 100 questions (totaling 300 run records across 3 agent variants) yielded:

| Metric | ReAct | Reflexion | Reflexion Adaptive |
|---|---:|---:|---:|
| Exact Match (EM) | 1.0000 | 1.0000 | 1.0000 |
| Avg Attempts | 1.0 | 1.0 | 1.0 |
| Avg Latency (ms) | 290 | 290 | 290 |
| Avg Token Estimate | 505 | 505 | 505 |

*Note: In the mock mode, correct paths resolve on attempt 1 because mock questions don't fail, providing a clean verification that all schemas compile and run correctly.*

### 2. Real LLM Mode Evaluation (Mini Dataset)
Running the real LLM endpoint (`meta/llama-3.1-8b-instruct`) on `data/hotpot_mini_2.json` generated actual model metrics and verified correct evaluations:

| Metric | ReAct | Reflexion | Reflexion Adaptive | Delta |
|---|---:|---:|---:|---:|
| Exact Match (EM) | 1.0000 | 1.0000 | 1.0000 | 0.0000 |
| Avg Attempts | 1.0 | 1.0 | 1.0 | 0.0 |
| Avg Latency (ms) | 5315.5 | 6236.0 | 6489.5 | +920.5 |
| Avg Token Estimate | 516.0 | 514.0 | 514.0 | -2.0 |

---

## 🎖️ Autograder Verification

Running `python autograde.py` validates the entire flow, schemas, experiment scope, and implementation depth:

```bash
Auto-grade total: 100/100
- Flow Score (Core): 80/80
  * Schema: 30/30
  * Experiment: 30/30
  * Analysis: 20/20
- Bonus Score: 20/20
```

### 💡 Implemented Extensions Listed
1. `structured_evaluator` — Enforced JSON validation on evaluator schema.
2. `reflection_memory` — Passed formatted correction feedback logs to the actor.
3. `benchmark_report_json` — Standardized output reporting to structured JSON logs.
4. `mock_mode_for_autograding` — Supported dual-mode runs (LLM vs Mock).
5. `adaptive_max_attempts` — Adjusted attempt budget dynamically based on metadata.
