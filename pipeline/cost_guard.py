"""Cost-guard: pre-flight gate that aborts before first Parallel call if
estimated cost exceeds the soft cap chosen in the wizard.
"""


class CostCapExceeded(Exception):
    """Raised when estimated Parallel cost exceeds the user-defined soft cap."""


def check_cost(preview_usd: float, soft_cap_usd: float) -> None:
    if preview_usd > soft_cap_usd:
        raise CostCapExceeded(
            f"preview ${preview_usd} exceeds soft cap ${soft_cap_usd} — "
            f"re-run with higher tier or raise cap"
        )
