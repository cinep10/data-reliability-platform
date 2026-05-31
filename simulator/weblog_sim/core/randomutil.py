from __future__ import annotations

import math
import random
import uuid
from typing import Any, Iterable, Sequence, Tuple


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def weighted_choice(items: Sequence[Tuple[Any, float]]) -> Any:
    total = sum(w for _, w in items)
    if total <= 0:
        return items[-1][0]
    r = random.random() * total
    acc = 0.0
    for v, w in items:
        acc += w
        if r <= acc:
            return v
    return items[-1][0]


def poisson(lmbd: float) -> int:
    if lmbd <= 0:
        return 0
    l = math.exp(-lmbd)
    k = 0
    p = 1.0
    while p > l:
        k += 1
        p *= random.random()
    return k - 1


def make_uuid() -> str:
    """Return a deterministic UUID backed by Python random.

    uuid.uuid4() reads OS entropy, which breaks same-seed source generation.
    This keeps the UUID format while making output reproducible after random.seed().
    """
    return str(uuid.UUID(int=random.getrandbits(128)))


def make_uid() -> str:
    prefix = random.choice(["USR", "MEM", "CID", "UID"])
    return f"{prefix}{random.randint(1000000, 9999999)}_{random.randint(10000000000, 99999999999)}"
