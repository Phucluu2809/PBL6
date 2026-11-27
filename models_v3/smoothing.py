"""Short symmetric filters for already recorded signals."""

import math


KERNELS = {
    "light3": (1 / 8, 6 / 8, 1 / 8),
    # Blend half of a quadratic Savitzky-Golay filter with the original point.
    "sg5_half": (-3 / 70, 12 / 70, 52 / 70, 12 / 70, -3 / 70),
}


def smooth(values, method, *, times=None):
    """Keep endpoints and any window that crosses a missing scan unchanged."""
    result = list(values)
    if method == "none":
        return result
    weights = KERNELS[method]
    radius = len(weights) // 2
    for index in range(radius, len(values) - radius):
        left, right = index - radius, index + radius + 1
        window = values[left:right]
        if any(value is None for value in window):
            continue
        if times is not None and any(
            not .9 <= finish - start <= 1.1
            for start, finish in zip(times[left:right-1], times[left+1:right])
        ):
            continue
        result[index] = math.fsum(weight * value for weight, value in zip(weights, window, strict=True))
    return result
