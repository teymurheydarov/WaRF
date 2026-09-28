"""
WaRF — Weighted n-Agent Reliability Framework.

Multi-agent code review: a panel of personas votes, each vote is weighted by
that agent's learned reliability in the domain, evidence accumulates under a
sequential probability ratio test, and the review stops as soon as a boundary
is crossed. Ground truth fed back with `warf label` updates the weights.

Library entry points:

    from warf.orchestrator import run_review, apply_oracle
    from warf.state import load_profiles, default_profiles
    from warf.paths import data_dir

Command line: `warf` once installed, or `python -m warf` from a checkout.
Interpretation rules for the output live in warf/policy.md.
"""

__version__ = "0.1.0"
