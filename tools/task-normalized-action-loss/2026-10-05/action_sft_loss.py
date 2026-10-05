"""Synthetic-only, task-balanced action-token negative log likelihood.

This module proves a weighting contract. It neither authenticates native model
captures nor supplies a tokenizer, trainer, teacher or repair evaluator.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class FixtureTrajectory:
    task_id: str
    trajectory_id: str
    token_ids: np.ndarray
    token_log_probs: np.ndarray
    prompt_mask: np.ndarray
    thought_mask: np.ndarray
    action_mask: np.ndarray
    padding_mask: np.ndarray
    outcome: str
    outcome_verified: bool
    outcome_provenance: str = "synthetic-fixture"


@dataclass(frozen=True)
class LossResult:
    loss: float
    token_weights: tuple[np.ndarray, ...]
    grad_log_probs: tuple[np.ndarray, ...]
    unique_tasks: int
    accepted_trajectories: int
    duplicate_rows: int
    exclusions: tuple[tuple[int, str], ...]
    synthetic_only: bool = True
    training_ready: bool = False


def _validate(row: FixtureTrajectory) -> str:
    if not isinstance(row, FixtureTrajectory):
        raise ValueError("Expected a FixtureTrajectory")
    if not isinstance(row.task_id, str) or not row.task_id.startswith("fixture/task/"):
        raise ValueError("A canonical synthetic task identity is required")
    if not isinstance(row.trajectory_id, str) or not row.trajectory_id.startswith("fixture/trajectory/"):
        raise ValueError("A canonical synthetic trajectory identity is required")
    if row.outcome_provenance != "synthetic-fixture":
        raise ValueError("Only explicit synthetic fixture provenance is supported")
    if row.outcome not in {"success", "failure", "unknown"}:
        raise ValueError("Unrecognized outcome")
    if type(row.outcome_verified) is not bool:
        raise ValueError("Outcome verification must be an explicit boolean")
    if row.outcome == "unknown" and row.outcome_verified:
        raise ValueError("An unknown outcome cannot be verified")
    ids = np.asarray(row.token_ids)
    lp = np.asarray(row.token_log_probs)
    if ids.ndim != 1 or ids.size == 0 or ids.dtype.kind not in "iu" or np.any(ids < 0):
        raise ValueError("Synthetic token identities must be a nonempty integer vector")
    if lp.shape != ids.shape or lp.dtype.kind != "f" or not np.all(np.isfinite(lp)) or np.any(lp > 0):
        raise ValueError("Finite nonpositive token log probabilities are required")
    masks = [np.asarray(m) for m in (row.prompt_mask, row.thought_mask, row.action_mask, row.padding_mask)]
    if any(m.dtype != np.bool_ or m.shape != ids.shape for m in masks):
        raise ValueError("Masks must be exact boolean vectors aligned with token identities")
    membership = np.sum(np.stack(masks).astype(np.uint8), axis=0)
    if not np.all(membership == 1):
        raise ValueError("Prompt, thought, action and padding masks must form a disjoint complete partition")
    payload = {
        "task": row.task_id, "trajectory": row.trajectory_id,
        "ids": ids.tolist(), "log_probs": lp.tolist(),
        "masks": [m.tolist() for m in masks],
        "outcome": row.outcome, "verified": row.outcome_verified,
        "provenance": row.outcome_provenance,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def action_sft_loss(rows: Sequence[FixtureTrajectory]) -> LossResult:
    """L = mean_task mean_accepted_trajectory mean_action_token(-log p).

    Exact repeated records with the same canonical identity count once. A
    conflicting copy raises. Repeated rows receive zero weight after the first
    occurrence; the total loss and aggregate gradient retain their meaning.
    With no accepted verified successes, loss and every gradient are zero.
    """
    rows = tuple(rows)
    fingerprints: dict[tuple[str, str], str] = {}
    accepted: dict[str, list[int]] = {}
    exclusions: list[tuple[int, str]] = []
    weights = []
    duplicates = 0
    for i, row in enumerate(rows):
        fingerprint = _validate(row)
        weights.append(np.zeros(np.asarray(row.token_ids).shape, dtype=np.float64))
        key = row.task_id, row.trajectory_id
        if key in fingerprints:
            if fingerprints[key] != fingerprint:
                raise ValueError("Conflicting records share a canonical trajectory identity")
            duplicates += 1
            continue
        fingerprints[key] = fingerprint
        if row.outcome != "success":
            exclusions.append((i, "outcome_" + row.outcome))
            continue
        if not row.outcome_verified:
            exclusions.append((i, "outcome_unverified"))
            continue
        if not np.any(row.action_mask):
            raise ValueError("An accepted success requires at least one action token")
        accepted.setdefault(row.task_id, []).append(i)
    tasks = len(accepted)
    for indices in accepted.values():
        trajectory_mass = 1.0 / (tasks * len(indices))
        for i in indices:
            mask = np.asarray(rows[i].action_mask)
            weights[i][mask] = trajectory_mass / int(np.count_nonzero(mask))
    loss = float(sum(-np.dot(w, np.asarray(r.token_log_probs, dtype=np.float64)) for r, w in zip(rows, weights)))
    gradients = [-w for w in weights]
    for a in weights + gradients:
        a.setflags(write=False)
    return LossResult(loss, tuple(weights), tuple(gradients), tasks,
                      sum(map(len, accepted.values())), duplicates, tuple(exclusions))
