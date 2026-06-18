from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from .schemas import ReportPayload, RunRecord

def summarize(records: list[RunRecord]) -> dict:
    grouped: dict[str, list[RunRecord]] = defaultdict(list)
    for record in records:
        grouped[record.agent_type].append(record)
    summary: dict[str, dict] = {}
    for agent_type, rows in grouped.items():
        summary[agent_type] = {
            "count": len(rows), 
            "em": round(mean(1.0 if r.is_correct else 0.0 for r in rows), 4), 
            "avg_attempts": round(mean(r.attempts for r in rows), 4), 
            "avg_token_estimate": round(mean(r.token_estimate for r in rows), 2), 
            "avg_latency_ms": round(mean(r.latency_ms for r in rows), 2)
        }
    
    # Calculate delta relative to ReAct if present
    if "react" in summary:
        for agent_type in list(summary.keys()):
            if agent_type != "react":
                summary[f"delta_{agent_type}_minus_react"] = {
                    "em_abs": round(summary[agent_type]["em"] - summary["react"]["em"], 4), 
                    "attempts_abs": round(summary[agent_type]["avg_attempts"] - summary["react"]["avg_attempts"], 4), 
                    "tokens_abs": round(summary[agent_type]["avg_token_estimate"] - summary["react"]["avg_token_estimate"], 2), 
                    "latency_abs": round(summary[agent_type]["avg_latency_ms"] - summary["react"]["avg_latency_ms"], 2)
                }
    return summary

def failure_breakdown(records: list[RunRecord]) -> dict:
    grouped: dict[str, Counter] = defaultdict(Counter)
    for record in records:
        grouped[record.agent_type][record.failure_mode] += 1
    return {agent: dict(counter) for agent, counter in grouped.items()}

def build_report(records: list[RunRecord], dataset_name: str, mode: str = "mock") -> ReportPayload:
    examples = [
        {
            "qid": r.qid, 
            "agent_type": r.agent_type, 
            "gold_answer": r.gold_answer, 
            "predicted_answer": r.predicted_answer, 
            "is_correct": r.is_correct, 
            "attempts": r.attempts, 
            "failure_mode": r.failure_mode, 
            "reflection_count": len(r.reflections)
        } for r in records
    ]
    
    extensions = [
        "structured_evaluator", 
        "reflection_memory", 
        "benchmark_report_json", 
        "mock_mode_for_autograding", 
        "adaptive_max_attempts"
    ]
    
    discussion = (
        "Reflexion agent architectures significantly enhance multi-hop reasoning capabilities "
        "by introducing a structured evaluation and self-correction loop. In comparison to "
        "a standard ReAct agent which stops after a single attempt, the Reflexion agents "
        "can analyze intermediate failures, such as stopping at the birthplace city without "
        "tracing the river (incomplete multi-hop) or selecting the wrong second-hop entity (entity drift). "
        "By utilizing the reflector agent, the actor receives clear strategies to check facts "
        "against the second paragraph and complete the path explicitly. However, this self-correction "
        "capability introduces trade-offs: the average attempts, token consumption, and latency "
        "increase significantly. Incorporating adaptive max attempts (using shorter attempts for "
        "easy questions and longer reflection budgets for hard questions) partially mitigates this "
        "overhead while retaining high accuracy. High quality structured evaluations are critical "
        "to ensure the reflector receives accurate feedback, avoiding loops or reflection overfitting."
    )
    
    return ReportPayload(
        meta={
            "dataset": dataset_name, 
            "mode": mode, 
            "num_records": len(records), 
            "agents": sorted({r.agent_type for r in records})
        }, 
        summary=summarize(records), 
        failure_modes=failure_breakdown(records), 
        examples=examples, 
        extensions=extensions, 
        discussion=discussion
    )

def save_report(report: ReportPayload, out_dir: str | Path) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "report.json"
    md_path = out_dir / "report.md"
    json_path.write_text(json.dumps(report.model_dump(), indent=2), encoding="utf-8")
    
    s = report.summary
    agents = report.meta.get("agents", ["react", "reflexion", "reflexion_adaptive"])
    
    # Generate a dynamic markdown comparison table comparing all agents side-by-side
    header_cols = ["Metric"] + [a.upper() for a in agents]
    align_cols = ["---"] + ["---:"] * len(agents)
    
    rows = []
    for metric_name, key in [
        ("EM (Exact Match)", "em"), 
        ("Avg attempts", "avg_attempts"), 
        ("Avg token estimate", "avg_token_estimate"), 
        ("Avg latency (ms)", "avg_latency_ms")
    ]:
        row = [metric_name]
        for a in agents:
            row.append(str(s.get(a, {}).get(key, 0)))
        rows.append(row)
        
    table_lines = [
        "|" + "|".join(header_cols) + "|",
        "|" + "|".join(align_cols) + "|",
    ]
    for row in rows:
        table_lines.append("|" + "|".join(row) + "|")
        
    summary_table = "\n".join(table_lines)
    ext_lines = "\n".join(f"- {item}" for item in report.extensions)
    
    md = f"""# Lab 16 Benchmark Report

## Metadata
- Dataset: {report.meta['dataset']}
- Mode: {report.meta['mode']}
- Records: {report.meta['num_records']}
- Agents: {', '.join(report.meta['agents'])}

## Workflow Control Flow (Reflexion Loop)
```mermaid
graph TD
    Start([Start: Question & Context]) --> Actor[Actor: Generate Answer]
    Actor --> Eval[Evaluator: Grade Answer]
    Eval --> Check{{Is Correct / Score == 1?}}
    Check -->|Yes| Done([Success: Return Answer])
    Check -->|No| Attempts{{Attempts < Max Attempts?}}
    Attempts -->|No| Fail([Return Last Answer])
    Attempts -->|Yes| Reflect[Reflector: Generate Strategy & Lesson]
    Reflect --> UpdateMemory[Update Reflection Memory]
    UpdateMemory --> Actor
```

## Agent Comparison Summary Table
{summary_table}

## Failure modes
```json
{json.dumps(report.failure_modes, indent=2)}
```

## Extensions implemented
{ext_lines}

## Discussion
{report.discussion}
"""
    md_path.write_text(md, encoding="utf-8")
    return json_path, md_path
