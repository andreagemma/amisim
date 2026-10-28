"""Volume-delay functions used to update link travel times."""

__all__ = ["bpr"]


def bpr(flow: float, capacity: float, t0: float, vdf_a: float = 0.15, vdf_b: float = 4.0, **kwargs) -> float:
    """Calculate the travel time using the Bureau of Public Roads (BPR) function.

    Args:
        flow: Traffic volume.
        capacity: Link capacity.
        t0: Free-flow travel time.
        vdf_a: BPR alpha parameter.
        vdf_b: BPR beta parameter.

    Returns:
        Travel time.
    """
    # flow, capacity, t0, vdf_a, and vdf_b are now passed explicitly as arguments

    if t0 is None:
        return 0.0
    return t0 * (1 + vdf_a * (flow / capacity) ** vdf_b) if capacity and capacity > 0 else t0


def bpr2(flow: float, capacity: float, t0: float, vdf_a: float = 0.15, vdf_b: float = 4.0, **kwargs) -> float:
    """Calculate the travel time using the Bureau of Public Roads (BPR) function.

    Args:
        flow: Traffic volume.
        capacity: Link capacity.
        t0: Free-flow travel time.
        vdf_a: BPR alpha parameter.
        vdf_b: BPR beta parameter.

    Returns:
        Travel time.
    """
    # flow, capacity, t0, vdf_a, and vdf_b are now passed explicitly as arguments

    if t0 is None:
        return 0.0
    return t0 * (1 + vdf_a * (flow / capacity) ** vdf_b) if capacity and capacity > 0 else t0
