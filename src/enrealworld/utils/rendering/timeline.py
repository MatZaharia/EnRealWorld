"""Uniform output timestamps, including the end pose."""

import math


def timestamps(first, last, start, end, fps):
    tolerance = 1e-8
    start = first if start is None else start
    end = last if end is None else end
    if start < first - tolerance or end > last + tolerance or end <= start:
        raise ValueError(f"Require start < end within [{first:.9g}, {last:.9g}] seconds")
    start, end = max(first, start), min(last, end)
    intervals = max(1, math.ceil((end - start) * fps - tolerance))
    return [start + i / fps for i in range(intervals)] + [end]
