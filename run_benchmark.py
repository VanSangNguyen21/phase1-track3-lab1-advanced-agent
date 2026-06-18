from __future__ import annotations
import json
import os
from pathlib import Path
import typer
from rich import print
from src.reflexion_lab.agents import ReActAgent, ReflexionAgent, ReflexionAdaptiveAgent
from src.reflexion_lab.reporting import build_report, save_report
from src.reflexion_lab.utils import load_dataset, save_jsonl

app = typer.Typer(add_completion=False)

@app.command()
def main(
    dataset: str = "data/hotpot_mini.json", 
    out_dir: str = "outputs/sample_run", 
    reflexion_attempts: int = 3,
    mode: str = "mock"
) -> None:
    # Set the execution mode for the runtime functions
    os.environ["REFLEXION_MODE"] = mode.lower()
    
    print(f"Loading dataset: [cyan]{dataset}[/cyan]")
    examples = load_dataset(dataset)
    print(f"Loaded {len(examples)} examples.")
    
    print(f"Initializing agents (mode: {mode})...")
    react = ReActAgent()
    reflexion = ReflexionAgent(max_attempts=reflexion_attempts)
    reflexion_adaptive = ReflexionAdaptiveAgent(max_attempts=reflexion_attempts)
    
    print("Running ReAct Agent...")
    react_records = [react.run(example) for example in examples]
    
    print("Running Reflexion Agent...")
    reflexion_records = [reflexion.run(example) for example in examples]
    
    print("Running Reflexion Adaptive Agent...")
    adaptive_records = [reflexion_adaptive.run(example) for example in examples]
    
    all_records = react_records + reflexion_records + adaptive_records
    
    out_path = Path(out_dir)
    save_jsonl(out_path / "react_runs.jsonl", react_records)
    save_jsonl(out_path / "reflexion_runs.jsonl", reflexion_records)
    save_jsonl(out_path / "reflexion_adaptive_runs.jsonl", adaptive_records)
    
    print(f"Building report (total records: {len(all_records)})...")
    report = build_report(all_records, dataset_name=Path(dataset).name, mode=mode)
    json_path, md_path = save_report(report, out_path)
    
    print(f"[green]Saved[/green] {json_path}")
    print(f"[green]Saved[/green] {md_path}")
    print("\nSummary Results:")
    print(json.dumps(report.summary, indent=2))

if __name__ == "__main__":
    app()
