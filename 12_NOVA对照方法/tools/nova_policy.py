"""Paper Algorithm 1/2 selection port, independent of the UCB policies.

Unspecified choices are frozen in configs/nova_17test.json and method_mapping.md.
No solver parameter optimization or runtime penalty is performed by this module.
"""
from dataclasses import dataclass
import math
import random

import numpy as np


@dataclass(frozen=True)
class Parameters:
    ensemble_size: int = 50
    samples_per_bin: int = 1
    sample_size: int = 8
    top_fraction: float = 0.005

    def __post_init__(self):
        for name in ('ensemble_size', 'samples_per_bin', 'sample_size'):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f'{name} must be a positive integer')
        if not math.isfinite(self.top_fraction) or not 0 < self.top_fraction <= 1:
            raise ValueError('top_fraction must be in (0, 1]')


class NovaSelector:
    def __init__(self, arms, cluster_indices, history, seed=42, parameters=None):
        self.arms = tuple(arms)
        if not self.arms or len(set(self.arms)) != len(self.arms):
            raise ValueError('Unique official test IDs are required')
        self.parameters = parameters or Parameters()
        self.rng = random.Random(seed)
        self.clusters = {str(k): np.asarray(v, dtype=int) for k, v in cluster_indices.items()}
        flattened = [int(i) for indices in self.clusters.values() for i in indices]
        if not flattened or any(len(v) == 0 for v in self.clusters.values()):
            raise ValueError('Empty coverage partition')
        self.bin_count = len(flattened)
        if sorted(flattened) != list(range(self.bin_count)):
            raise ValueError('Clusters must partition the complete bin universe exactly once')
        self.vectors, self.owners = [], []
        self.by_arm = {arm: [] for arm in self.arms}
        self.active = {arm: 0 for arm in self.arms}
        self.union = np.zeros(self.bin_count, dtype=bool)
        for arm, vector in history:
            self.add(arm, vector)
        if not self.vectors:
            raise ValueError('Warm-up observations are required')

    def add(self, arm, vector):
        if arm not in self.by_arm:
            raise ValueError(f'Unknown test ID: {arm}')
        array = np.asarray(vector)
        if array.shape != (self.bin_count,) or not np.isin(array, (0, 1)).all():
            raise ValueError('Coverage feedback must be a binary vector in the frozen bin order')
        array = array.astype(bool, copy=True)
        self.by_arm[arm].append(len(self.vectors))
        self.vectors.append(array)
        self.owners.append(arm)
        self.union |= array

    def reserve(self, arm):
        self.active[arm] += 1

    def feedback(self, arm, vector=None):
        if self.active[arm] <= 0:
            raise ValueError('Feedback has no corresponding active submission')
        self.active[arm] -= 1
        if vector is not None:
            self.add(arm, vector)

    def target_cluster(self):
        # Overview, page 3: largest remaining uncovered space. Coverage fraction
        # is a local secondary tie-breaker; catalog-independent seeded ties.
        candidates = []
        for cluster, indices in self.clusters.items():
            hits = int(self.union[indices].sum())
            if hits < len(indices):
                candidates.append((cluster, len(indices) - hits, hits / len(indices)))
        if not candidates:
            return None
        maximum = max(c[1] for c in candidates)
        fraction = min(c[2] for c in candidates if c[1] == maximum)
        ties = sorted(c[0] for c in candidates if c[1] == maximum and c[2] == fraction)
        return self.rng.choice(ties)

    def sample_ensemble(self, cluster):
        indices = self.clusters[cluster]
        matrix = np.asarray(self.vectors, dtype=bool)[:, indices]
        covering = [np.flatnonzero(matrix[:, i]).tolist() for i in range(len(indices))]
        p = self.parameters
        ensemble, empty_fallbacks = [], 0
        for _ in range(p.ensemble_size):
            balanced = set()
            for pool in covering:
                if pool:
                    balanced.update(self.rng.sample(pool, min(p.samples_per_bin, len(pool))))
            if not balanced:
                # No vector can cover an unobserved bin. Algorithm 2 does not
                # define this case: use all history, record the local fallback.
                balanced.update(range(len(self.vectors)))
                empty_fallbacks += 1
            pool = sorted(balanced)
            ensemble.append(self.rng.sample(pool, min(p.sample_size, len(pool))))
        return ensemble, empty_fallbacks

    def novelty_scores(self, cluster, ensemble):
        x = np.asarray(self.vectors, dtype=bool)[:, self.clusters[cluster]]
        distances = np.zeros(len(x), dtype=float)
        for subset in ensemble:
            if not subset:
                raise ValueError('Empty ensemble subset')
            # Euclidean distance on binary vectors = sqrt(Hamming count).
            # Bound intermediate memory: at most 256 * sample_size * |g| bits.
            for start in range(0, len(x), 256):
                block = x[start:start + 256]
                squared = np.count_nonzero(block[:, None, :] != x[subset][None, :, :], axis=2)
                distances[start:start + len(block)] += np.sqrt(squared.min(axis=1))
        scores = {}
        for arm, rows in self.by_arm.items():
            if not rows:
                raise ValueError('Empty categories must finish cold-start before scoring')
            values = distances[rows]
            count = max(1, math.ceil(len(values) * self.parameters.top_fraction))
            scores[arm] = float(np.sort(values)[-count:].mean())
        return scores

    def choose(self):
        target = self.target_cluster()
        if target is None:
            return None, {'rule': 'coverage_closed', 'target': None, 'scores': None}
        # The shared prior has only 4/17 arms. Cover the other arms in formal
        # budget, reserving in-flight arms to avoid 10 duplicates at startup.
        empty = [arm for arm in self.arms if not self.by_arm[arm]]
        if empty:
            least = min(self.active[arm] for arm in empty)
            arm = self.rng.choice([arm for arm in empty if self.active[arm] == least])
            return arm, {'rule': 'cold_start_empty_history', 'target': target,
                         'scores': None, 'empty_history_arms': empty}
        ensemble, fallbacks = self.sample_ensemble(target)
        scores = self.novelty_scores(target, ensemble)
        maximum = max(scores.values())
        ties = [arm for arm in self.arms if scores[arm] == maximum]
        arm = self.rng.choice(ties)
        return arm, {'rule': 'nova_top_fraction_ensemble_nn', 'target': target,
                     'scores': scores, 'empty_ensemble_fallbacks': fallbacks,
                     'ensemble_history_indices': ensemble}
