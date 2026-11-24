"""Pixeltable evaluation for the synthetic lifecycle."""

from typing import Any

import pixeltable as pxt


@pxt.udf
def passes_lifecycle(metrics: dict[str, Any]) -> bool:
    if not metrics:
        return False
    return bool(
        metrics["late_visible_before_dream"]
        and metrics["late_memory"]
        and metrics["late_retrievable_after_dream"]
        and metrics["contradictions"]
        and metrics["decayed_memories"]
        and metrics["other_user_recall"]
        and metrics["noop_checkpoints"] == 0
        and metrics["duplicate_fact_rows"] == 0
        and not metrics["cross_branch_chunk"]
        and not metrics["cross_user_before_dream"]
        and not metrics["cross_user_after_dream"]
        and metrics["durable_facts_found"] == metrics["expected_facts"]
        and metrics["restart_recall"] == 1
    )
