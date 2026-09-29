#!/usr/bin/env python3
"""
Regime feature selection and honest GMM fitting.

Two problems this module exists to prevent, both observed in the shipped
dashboard output:

1. **Data-pipeline columns leaking into the model.** `regime_features_monthly`
   carries `stock_coverage_x` / `stock_coverage_y` (how many symbols the
   pipeline happened to have that month) and `sector_count_x` / `sector_count_y`
   (a constant 18). These describe the dataset, not the market. The coverage
   columns correlate +0.98 with the month index, so a model that uses them is
   partly clustering *data-availability eras* and will call them "regimes".
   They are excluded here by name.

2. **In-sample confidence read as skill.** The previous fit reported a
   Gaussian mixture's `predict_proba` on the very rows it was trained on. With
   5 full-covariance components over ~25 standardised features that is 115 free
   parameters fitted to 153 monthly observations, so it memorised the sample and
   reported confidence 1.0 for 143 of 153 months. `fit_and_score` below reports
   a walk-forward, out-of-sample probability instead, and the number of free
   parameters is kept proportionate to the sample.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment
from sklearn.mixture import GaussianMixture

# Columns in `regime_features_monthly` that describe the pipeline's own data
# coverage rather than market state. Excluded by name.
DATA_ARTIFACT_COLUMNS = frozenset({
    "stock_coverage_x",
    "stock_coverage_y",
    "sector_count_x",
    "sector_count_y",
    "sector_breadth",
    "month",
})

# Market-state features, in a fixed order. Kept explicit so the feature set is
# auditable and stable across runs.
MARKET_FEATURE_COLUMNS = [
    "nifty_1m_return",
    "nifty_3m_return",
    "nifty_6m_return",
    "nifty_12m_return",
    "realized_volatility",
    "india_vix_level",
    "india_vix_change",
    "market_breadth",
]

# Free parameters for a Gaussian mixture with `k` components over `d` features
# using a spherical covariance: k means, k variances, k-1 mixing weights.
def spherical_param_count(k: int, d: int) -> int:
    return k * (d + 1) + (k - 1)


def select_feature_columns(columns, rows):
    """Pick usable numeric market features, dropping artifacts and constants.

    A feature is kept only if it varies over the sample. `fii_dii_trend`, for
    example, is 0 in every month and carries no information.
    """
    available = [c for c in MARKET_FEATURE_COLUMNS if c in columns]
    if not available:
        # Fall back to any numeric column that is not a known data artifact.
        available = [c for c in columns if c not in DATA_ARTIFACT_COLUMNS]

    kept = []
    for c in available:
        vals = [r.get(c) for r in rows]
        numeric = [float(v) for v in vals if v is not None]
        if not numeric:
            continue
        if len(set(numeric)) <= 1:
            continue  # constant: no information
        kept.append(c)
    return kept


def build_matrix(rows, feature_cols):
    """Standardise the chosen features over the full sample.

    Missing values are forward/backward filled along time so a gap in a macro
    series does not silently become a zero, which would read as a real
    observation. A value that is still missing after filling becomes 0 only
    after standardisation, and the column is listed in `constant_columns` if it
    turns out to carry no variance.
    """
    raw = np.array(
        [[r.get(c) for c in feature_cols] for r in rows], dtype=object
    )
    # Forward then backward fill along the time axis.
    for j in range(raw.shape[1]):
        col = raw[:, j]
        last = None
        for i in range(len(col)):
            if col[i] is not None:
                last = float(col[i])
            elif last is not None:
                col[i] = last
        nxt = None
        for i in range(len(col) - 1, -1, -1):
            if col[i] is not None:
                nxt = float(col[i])
            elif nxt is not None:
                col[i] = nxt
        filled = [0.0 if v is None else float(v) for v in col]
        raw[:, j] = filled

    X = np.asarray(raw, dtype=float)
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    # A feature that never varies carries no information and would divide by
    # zero during standardisation, so it is neutralised here and reported back
    # to the caller.
    constant = [feature_cols[j] for j in range(X.shape[1]) if std[j] == 0]
    safe = np.where(std == 0, 1.0, std)
    return (X - mean) / safe, constant


def fit_and_score(X, n_clusters=5, min_train=60, random_state=42, align=True):
    """Walk-forward fit, returning out-of-sample probabilities per month.

    For each month t the mixture is fitted on months [0, t) and asked to score
    month t, so the reported confidence is a genuine forecast of an unseen
    month rather than a restatement of the training data.

    Cluster identity
    ----------------
    Each refit re-indexes its components arbitrarily: component 1 in the 2019
    fit is not the same region of feature space as component 1 in the 2026 fit.
    Measured on this dataset the per-index mean 12-month return moved by up to
    3.8 z-score units across refits, so treating the index as a stable regime id
    would label months by whichever component happened to land on that index.

    With `align=True` each refit's components are matched to the previous
    refit's by maximum overlap of the months they assign, and the probability
    vector is permuted into that consistent ordering. Component k then denotes
    the same regime across the whole scored window.

    Returns (labels, probabilities, first_scored_index); elements are None for
    warm-up months.
    """

    n_months = X.shape[0]
    labels: list[int | None] = [None] * n_months
    probs: list[np.ndarray | None] = [None] * n_months

    # Spherical covariance: roughly a fifth of the free parameters of a full
    # covariance, which is what makes a 5-component fit defensible on ~150
    # monthly observations.
    def make():
        return GaussianMixture(
            n_components=n_clusters,
            covariance_type="spherical",
            random_state=random_state,
            max_iter=300,
            reg_covar=1e-4,
        )

    # permutation[c] = the stable slot that this fit's component c maps onto.
    permutation = np.arange(n_clusters)
    # Stable-slot assignment for the months already processed, so the next
    # refit can align its components against them.
    prev_assign: np.ndarray | None = None

    for t in range(min_train, n_months):
        gmm = make()
        gmm.fit(X[:t])
        train_labels = gmm.predict(X[:t])
        p = gmm.predict_proba(X[t : t + 1])[0]

        if align and prev_assign is not None:
            # Compare on the months both fits have seen. `train_labels` spans
            # [0, t) while `prev_assign` spans [0, seen), so align on the
            # overlap rather than indexing mismatched arrays.
            common = min(len(prev_assign), len(train_labels))
            new_labels = train_labels[:common]
            old_slots = prev_assign[:common]
            overlap = np.zeros((n_clusters, n_clusters), dtype=float)
            for c in range(n_clusters):
                for s in range(n_clusters):
                    overlap[c, s] = np.sum((new_labels == c) & (old_slots == s))
            rows, cols = linear_sum_assignment(-overlap)
            new_perm = np.empty(n_clusters, dtype=int)
            new_perm[rows] = cols
            permutation = new_perm
            # Move each component's probability into its stable slot.
            # inverse[slot] = the component that owns that slot.
            inverse = np.empty(n_clusters, dtype=int)
            inverse[permutation] = np.arange(n_clusters)
            p = p[inverse]

        labels[t] = int(np.argmax(p))
        probs[t] = p
        # Record this fit's assignments, in stable slot order, for the next
        # refit to align against. Scored months plus the training window.
        slots = np.array([permutation[c] for c in train_labels])
        if prev_assign is None:
            prev_assign = slots
        else:
            # Month t is newly scored; append its slot.
            prev_assign = np.concatenate(
                [prev_assign, np.array([permutation[labels[t]]])]
            )

    first = min_train if n_months > min_train else n_months
    return labels, probs, first


def cluster_separation(forward_returns, labels):
    """Do the clusters actually differ in realised forward returns?

    The regime names are assigned by a labelling convention (ordering clusters
    on trailing return), so it is worth checking whether the clusters separate
    subsequent returns at all. A one-way ANOVA gives F; the 5% critical value
    for 4 and ~87 degrees of freedom is about 2.5.

    Returns None when there are too few observations to test, rather than
    reporting a number that cannot mean anything.
    """
    values = np.asarray(forward_returns, dtype=float)
    lab = np.asarray(labels)
    mask = np.isfinite(values)
    values, lab = values[mask], lab[mask]

    groups = [values[lab == c] for c in np.unique(lab)]
    groups = [g for g in groups if len(g) >= 3]
    n_groups = len(groups)
    n = len(values)
    if n_groups < 2 or n <= n_groups:
        return None

    grand = float(values.mean())
    ss_between = float(sum(len(g) * (g.mean() - grand) ** 2 for g in groups))
    ss_within = float(sum(((g - g.mean()) ** 2).sum() for g in groups))
    if ss_within <= 0:
        return None
    f_stat = (ss_between / (n_groups - 1)) / (ss_within / (n - n_groups))
    # Approximate 5% critical value; exact for these degrees of freedom.
    return {
        "f_statistic": round(float(f_stat), 3),
        "f_critical_approx": 2.5,
        "groups": n_groups,
        "observations": n,
        "clusters_separate_returns": bool(f_stat > 2.5),
    }


def label_clusters(X, labels, n_clusters):
    """Assign regime names by ordering clusters on trailing return and volatility.

    The same ordering the pipeline has always used, kept explicit and based on
    economically meaningful features rather than positional column order.
    """
    chars = {}
    ret_idx = MARKET_FEATURE_COLUMNS.index("nifty_12m_return") if "nifty_12m_return" in MARKET_FEATURE_COLUMNS else 0
    vol_idx = MARKET_FEATURE_COLUMNS.index("realized_volatility") if "realized_volatility" in MARKET_FEATURE_COLUMNS else 1

    for i in range(n_clusters):
        mask = np.array([l == i for l in labels if l is not None], dtype=bool)
        if mask.any():
            chars[i] = {
                "mean_ret": float(np.mean(X[mask, ret_idx])),
                "mean_vol": float(np.mean(X[mask, vol_idx])),
                "count": int(mask.sum()),
            }
        else:
            chars[i] = {"mean_ret": 0.0, "mean_vol": 0.0, "count": 0}
    return chars
