"""rlvr — verifier-adequacy instrumentation for code-RL rewards.

Live plan: docs/07-rescope-verifier-adequacy.md. Measure the verifier before
training against it: sandboxed execution (sandbox), frozen splits and dataset
access (data), pass@k + CIs (metrics), run manifests and trajectory logs
(manifest, trajectory), mutation-score audit (Phase B scripts).
"""

__version__ = "0.1.0"
