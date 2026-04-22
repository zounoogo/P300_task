"""
trial_generator.py
------------------
Generates randomized trial sequences for the P300 oddball experiment.

Rules enforced
--------------
- Exact target probability per block (e.g. 20 %).
- No more than N consecutive standards (configurable).
- Each block is generated independently.
- Trial IDs are continuous across blocks.
- Up to MAX_ATTEMPTS random shuffles before falling back to a
  deterministic valid sequence.
"""

import random
from typing import List, Tuple

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

STANDARD = "standard"   # blue circle  → LSL marker 11
TARGET   = "target"     # red circle   → LSL marker 22

MAX_ATTEMPTS = 100      # shuffle retries before deterministic fallback


# ─────────────────────────────────────────────
# Core data structure
# ─────────────────────────────────────────────

class Trial:
    """Holds all static information about one trial."""

    __slots__ = (
        "trial_id",
        "block_id",
        "stimulus_type",
        "is_practice",
    )

    def __init__(
        self,
        trial_id: int,
        block_id: int,
        stimulus_type: str,
        is_practice: bool = False,
    ):
        self.trial_id      = trial_id
        self.block_id      = block_id
        self.stimulus_type = stimulus_type   # STANDARD or TARGET
        self.is_practice   = is_practice

    @property
    def lsl_code(self) -> int:
        """Return the LSL marker integer for this trial's stimulus."""
        return 11 if self.stimulus_type == STANDARD else 22

    def __repr__(self) -> str:
        tag = "P" if self.is_practice else "M"
        return (
            f"Trial(id={self.trial_id}, block={self.block_id}, "
            f"type={self.stimulus_type}, [{tag}])"
        )


# ─────────────────────────────────────────────
# Constraint checker
# ─────────────────────────────────────────────

def _has_too_many_consecutive(
    sequence: List[str],
    max_consecutive_standards: int,
) -> bool:
    """
    Return True if *sequence* contains more than
    *max_consecutive_standards* standards in a row.
    """
    count = 0
    for s in sequence:
        if s == STANDARD:
            count += 1
            if count > max_consecutive_standards:
                return True
        else:
            count = 0
    return False


# ─────────────────────────────────────────────
# Deterministic fallback
# ─────────────────────────────────────────────

def _deterministic_sequence(
    n_standards: int,
    n_targets: int,
    max_consecutive_standards: int,
) -> List[str]:
    """
    Build a valid sequence by interleaving targets at fixed intervals.
    Guarantees the consecutive constraint is respected.
    """
    seq: List[str] = []
    targets_left = n_targets
    standards_left = n_standards
    interval = max(1, max_consecutive_standards)

    placed = 0
    while standards_left > 0 or targets_left > 0:
        # Place up to *interval* standards then one target
        batch = min(interval, standards_left)
        seq.extend([STANDARD] * batch)
        standards_left -= batch
        placed += batch

        if targets_left > 0:
            seq.append(TARGET)
            targets_left -= 1

    # Append leftover targets if any
    seq.extend([TARGET] * targets_left)
    return seq


# ─────────────────────────────────────────────
# Single-block generator
# ─────────────────────────────────────────────

def _generate_block_sequence(
    trials_per_block: int,
    target_probability: float,
    max_consecutive_standards: int,
    rng: random.Random,
) -> List[str]:
    """
    Return a list of STANDARD/TARGET strings for one block.

    Tries random shuffles first; falls back to deterministic if needed.
    """
    n_targets   = round(trials_per_block * target_probability)
    n_targets   = max(1, min(n_targets, trials_per_block - 1))
    n_standards = trials_per_block - n_targets

    pool = [STANDARD] * n_standards + [TARGET] * n_targets

    for attempt in range(MAX_ATTEMPTS):
        rng.shuffle(pool)
        if not _has_too_many_consecutive(pool, max_consecutive_standards):
            print(
                f"[trial_generator] Valid shuffle found on attempt {attempt + 1}."
            )
            return pool[:]

    # Fallback
    print(
        "[trial_generator] WARNING: Could not find valid shuffle after "
        f"{MAX_ATTEMPTS} attempts. Using deterministic sequence."
    )
    return _deterministic_sequence(n_standards, n_targets, max_consecutive_standards)


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def generate_trials(
    total_trials: int,
    n_blocks: int,
    target_probability: float   = 0.20,
    max_consecutive_standards: int = 5,
    seed: int | None            = None,
) -> List[List[Trial]]:
    """
    Generate all trial blocks for the main experiment.

    Args:
        total_trials              : total number of trials across all blocks
        n_blocks                  : number of blocks
        target_probability        : fraction of trials that are targets (default 0.20)
        max_consecutive_standards : maximum standards in a row (default 5)
        seed                      : optional RNG seed for reproducibility

    Returns:
        List of blocks; each block is a list of Trial objects.
        Trial IDs are continuous: 1 … total_trials.
    """
    rng = random.Random(seed)
    trials_per_block = total_trials // n_blocks
    remainder        = total_trials % n_blocks

    all_blocks: List[List[Trial]] = []
    global_id = 1

    for block_idx in range(n_blocks):
        # Distribute remainder trials into early blocks
        block_size = trials_per_block + (1 if block_idx < remainder else 0)

        sequence = _generate_block_sequence(
            block_size,
            target_probability,
            max_consecutive_standards,
            rng,
        )

        block_trials = []
        for stim_type in sequence:
            block_trials.append(
                Trial(
                    trial_id      = global_id,
                    block_id      = block_idx + 1,
                    stimulus_type = stim_type,
                    is_practice   = False,
                )
            )
            global_id += 1

        all_blocks.append(block_trials)
        _log_block_stats(block_idx + 1, block_trials)

    return all_blocks


def generate_practice_trials(
    n_trials: int                  = 30,
    target_probability: float      = 0.20,
    max_consecutive_standards: int = 5,
    seed: int | None               = None,
) -> List[Trial]:
    """
    Generate a single practice block.

    Returns:
        Flat list of Trial objects (is_practice=True).
        Trial IDs start at 1.
    """
    rng = random.Random(seed)

    sequence = _generate_block_sequence(
        n_trials,
        target_probability,
        max_consecutive_standards,
        rng,
    )

    trials = [
        Trial(
            trial_id      = idx + 1,
            block_id      = 0,          # block 0 = practice
            stimulus_type = stim_type,
            is_practice   = True,
        )
        for idx, stim_type in enumerate(sequence)
    ]

    _log_block_stats("practice", trials)
    return trials


# ─────────────────────────────────────────────
# Internal logging helper
# ─────────────────────────────────────────────

def _log_block_stats(label, trials: List[Trial]) -> None:
    n_total    = len(trials)
    n_targets  = sum(1 for t in trials if t.stimulus_type == TARGET)
    n_standards = n_total - n_targets
    pct = 100 * n_targets / n_total if n_total else 0
    print(
        f"[trial_generator] Block {label}: "
        f"{n_total} trials | "
        f"{n_standards} standards | "
        f"{n_targets} targets ({pct:.1f} %)"
    )


# ─────────────────────────────────────────────
# Quick self-test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Practice block ===")
    practice = generate_practice_trials(n_trials=30, seed=42)
    print(practice[:5], "...\n")

    print("=== Main experiment (600 trials, 6 blocks) ===")
    blocks = generate_trials(
        total_trials=600,
        n_blocks=6,
        target_probability=0.20,
        max_consecutive_standards=5,
        seed=42,
    )
    print(f"Total blocks: {len(blocks)}")
    print(f"First trial : {blocks[0][0]}")
    print(f"Last trial  : {blocks[-1][-1]}")