from __future__ import annotations
import os
import time
import requests
from dotenv import load_dotenv
from .schemas import QAExample, JudgeResult, ReflectionEntry
from .utils import normalize_answer

load_dotenv()

# Load from env or .env file (which is ignored by Git)
API_KEY = os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://integrate.api.nvidia.com/v1")
MODEL_NAME = os.getenv("LLM_MODEL", "meta/llama-3.1-8b-instruct")

# Global metrics tracking for the last call
_last_tokens = 0
_last_latency = 0
_last_request_time = 0.0

def reset_metrics():
    global _last_tokens, _last_latency
    _last_tokens = 0
    _last_latency = 0

def get_last_metrics() -> tuple[int, int]:
    return _last_tokens, _last_latency

def call_llm(system_prompt: str, user_prompt: str, json_mode: bool = False) -> tuple[str, int, int]:
    global _last_tokens, _last_latency, _last_request_time
    
    if not API_KEY:
        raise ValueError("OPENAI_API_KEY environment variable is not set. Please configure it in your local .env file.")
        
    # Rate Limiting: Enforce a minimum delay of 3 seconds between calls for stability
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < 3.0:
        sleep_time = 3.0 - elapsed
        time.sleep(sleep_time)
        
    url = f"{BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.0,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
        
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    max_retries = 5
    backoff = 5.0
    
    for attempt in range(max_retries):
        try:
            _last_request_time = time.time()
            response = requests.post(url, json=payload, headers=headers, timeout=45)
            if response.status_code == 200:
                res_json = response.json()
                content = res_json["choices"][0]["message"]["content"]
                usage = res_json.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                return content, prompt_tokens, completion_tokens
            elif response.status_code == 429:
                print(f"Rate limited (429). Retrying in {backoff} seconds... (Attempt {attempt+1}/{max_retries})")
                time.sleep(backoff)
                backoff *= 2
            else:
                raise RuntimeError(f"LLM API Error {response.status_code}: {response.text}")
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"Error calling LLM after {max_retries} attempts: {e}")
                raise e
            print(f"Transient error calling LLM: {e}. Retrying in {backoff} seconds...")
            time.sleep(backoff)
            backoff *= 2
            
    raise RuntimeError("Failed to call LLM after maximum retries due to rate limiting or errors.")

FIRST_ATTEMPT_WRONG = {"hp2": "London", "hp4": "Atlantic Ocean", "hp6": "Red Sea", "hp8": "Andes"}
FAILURE_MODE_BY_QID = {"hp2": "incomplete_multi_hop", "hp4": "wrong_final_answer", "hp6": "entity_drift", "hp8": "entity_drift"}

def actor_answer(example: QAExample, attempt_id: int, agent_type: str, reflection_memory: list[str]) -> str:
    global _last_tokens, _last_latency
    
    mode = os.getenv("REFLEXION_MODE", "mock").lower()
    if mode == "mock":
        _last_tokens = 320 + (attempt_id * 65)
        _last_latency = 160 + (attempt_id * 40)
        if example.qid not in FIRST_ATTEMPT_WRONG:
            return example.gold_answer
        if agent_type == "react":
            return FIRST_ATTEMPT_WRONG[example.qid]
        if attempt_id == 1 and not reflection_memory:
            return FIRST_ATTEMPT_WRONG[example.qid]
        return example.gold_answer

    # Real LLM logic
    from .prompts import ACTOR_SYSTEM
    
    context_str = "\n\n".join([f"Document: {c.title}\n{c.text}" for c in example.context])
    user_prompt = f"Question: {example.question}\n\nContext:\n{context_str}\n"
    
    if reflection_memory:
        reflections_str = "\n".join([f"- {ref}" for ref in reflection_memory])
        user_prompt += f"\nHere are reflections/strategies from your previous attempts. Please learn from them and do NOT repeat the same mistakes:\n{reflections_str}\n"
        
    user_prompt += "\nAnswer the question directly and concisely, using only the facts from the context. Do not add any extra text or conversational filler."
    
    start_time = time.time()
    content, p_tok, c_tok = call_llm(ACTOR_SYSTEM, user_prompt, json_mode=False)
    _last_latency = int((time.time() - start_time) * 1000)
    _last_tokens = p_tok + c_tok
    
    return content.strip()

def evaluator(example: QAExample, answer: str) -> JudgeResult:
    global _last_tokens, _last_latency
    
    mode = os.getenv("REFLEXION_MODE", "mock").lower()
    if mode == "mock":
        _last_tokens = 120
        _last_latency = 90
        if normalize_answer(example.gold_answer) == normalize_answer(answer):
            return JudgeResult(score=1, reason="Final answer matches the gold answer after normalization.")
        if normalize_answer(answer) == "london":
            return JudgeResult(score=0, reason="The answer stopped at the birthplace city and never completed the second hop to the river.", missing_evidence=["Need to identify the river that flows through London."], spurious_claims=[])
        return JudgeResult(score=0, reason="The final answer selected the wrong second-hop entity.", missing_evidence=["Need to ground the answer in the second paragraph."], spurious_claims=[answer])

    # Real LLM logic
    from .prompts import EVALUATOR_SYSTEM
    
    user_prompt = f"Question: {example.question}\nGold Answer (Correct): {example.gold_answer}\nPredicted Answer: {answer}\n"
    
    start_time = time.time()
    content, p_tok, c_tok = call_llm(EVALUATOR_SYSTEM, user_prompt, json_mode=True)
    _last_latency = int((time.time() - start_time) * 1000)
    _last_tokens = p_tok + c_tok
    
    try:
        cleaned_content = content.strip()
        if cleaned_content.startswith("```json"):
            cleaned_content = cleaned_content[7:]
        if cleaned_content.endswith("```"):
            cleaned_content = cleaned_content[:-3]
        cleaned_content = cleaned_content.strip()
        
        return JudgeResult.model_validate_json(cleaned_content)
    except Exception as e:
        print(f"Error parsing JudgeResult from evaluator output: {e}\nRaw output: {content}")
        is_correct = normalize_answer(example.gold_answer) == normalize_answer(answer)
        return JudgeResult(
            score=1 if is_correct else 0,
            reason=f"Fallback evaluation. JSON parsing error. Answer correct: {is_correct}",
            missing_evidence=[] if is_correct else [f"Could not verify correctness, fallback compared {answer} to {example.gold_answer}"],
            spurious_claims=[]
        )

def reflector(example: QAExample, attempt_id: int, judge: JudgeResult, answer: str = "") -> ReflectionEntry:
    global _last_tokens, _last_latency
    
    mode = os.getenv("REFLEXION_MODE", "mock").lower()
    if mode == "mock":
        _last_tokens = 150
        _last_latency = 110
        strategy = "Do the second hop explicitly: birthplace city -> river through that city." if example.qid == "hp2" else "Verify the final entity against the second paragraph before answering."
        return ReflectionEntry(attempt_id=attempt_id, failure_reason=judge.reason, lesson="A partial first-hop answer is not enough; the final answer must complete all hops.", next_strategy=strategy)

    # Real LLM logic
    from .prompts import REFLECTOR_SYSTEM
    
    user_prompt = f"Question: {example.question}\nGold Answer (Correct): {example.gold_answer}\nIncorrect Answer: {answer}\nFailure Reason: {judge.reason}\n"
    
    start_time = time.time()
    content, p_tok, c_tok = call_llm(REFLECTOR_SYSTEM, user_prompt, json_mode=True)
    _last_latency = int((time.time() - start_time) * 1000)
    _last_tokens = p_tok + c_tok
    
    try:
        cleaned_content = content.strip()
        if cleaned_content.startswith("```json"):
            cleaned_content = cleaned_content[7:]
        if cleaned_content.endswith("```"):
            cleaned_content = cleaned_content[:-3]
        cleaned_content = cleaned_content.strip()
        
        return ReflectionEntry.model_validate_json(cleaned_content)
    except Exception as e:
        print(f"Error parsing ReflectionEntry from reflector output: {e}\nRaw output: {content}")
        return ReflectionEntry(
            attempt_id=attempt_id,
            failure_reason=judge.reason,
            lesson="Failed to produce correct answer.",
            next_strategy="Re-read the question and context step-by-step."
        )
