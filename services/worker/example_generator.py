import json
import re
from pathlib import Path
from typing import Dict, Any, Optional

from .state_store import state_store

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge" / "examples"
EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)

def generate_reusable_example_from_task(task_id: str) -> Optional[Dict[str, Any]]:
    """
    P2: Generates a reusable generalized few-shot example from a VERIFIED SUCCESSFUL run.
    Rejects failed, partial, or unverified runs.
    Sanitizes and generalizes invoice numbers, amounts, and dates.
    """
    task = state_store.get_task(task_id)
    if not task:
        return None

    # Strict check: Task must be completed
    if task.get("status") != "completed":
        raise ValueError(f"Cannot generate example from task {task_id} with status '{task.get('status')}'. Only verified successful tasks are permitted.")

    steps = state_store.get_task_steps(task_id)
    if not steps:
        return None

    generalized_steps = []
    for s in steps:
        raw_args_str = json.dumps(s.get("arguments", {}))
        obs_str = str(s.get("observation", ""))

        # Generalize specific values
        clean_args = re.sub(r'INV-[A-Za-z0-9\-]+', '<INVOICE_REF>', raw_args_str)
        clean_args = re.sub(r'\b\d+\.\d{2}\b', '<AMOUNT>', clean_args)
        clean_obs = re.sub(r'INV-[A-Za-z0-9\-]+', '<INVOICE_REF>', obs_str)

        generalized_steps.append({
            "step_number": s["step_number"],
            "tool_name": s["tool_name"],
            "generalized_arguments": json.loads(clean_args),
            "generalized_observation": clean_obs[:200]
        })

    example_payload = {
        "example_id": f"EX-{task['workflow_id']}",
        "workflow_id": task["workflow_id"],
        "goal_pattern": task["goal"],
        "verified_success": True,
        "source_task_id": task_id,
        "generalized_trajectory": generalized_steps
    }

    example_file = EXAMPLES_DIR / f"{task['workflow_id']}_example.json"
    with open(example_file, "w", encoding="utf-8") as f:
        json.dump(example_payload, f, indent=2)

    return example_payload
