"""Tested building blocks for forthcoming wide/longitudinal exports and reports."""
from datetime import date
from math import isfinite
from statistics import mean, stdev


def eligible_history(records, index_date, lookback_days=None, include_index_day=False):
    index = date.fromisoformat(str(index_date)[:10])
    if lookback_days is not None and lookback_days <= 0:
        raise ValueError("lookback_days must be positive")
    result = []
    for row in records:
        if not row.get("event_date"):
            continue
        event = date.fromisoformat(str(row["event_date"])[:10])
        elapsed = (index - event).days
        if elapsed < 0 or (elapsed == 0 and not include_index_day):
            continue
        if lookback_days is not None and elapsed > lookback_days:
            continue
        result.append(dict(row))
    return sorted(result, key=lambda row: (row["event_date"], str(row.get("event_id", ""))))


def safe_numeric_mean(records, dimensionless=False):
    numeric = [row for row in records if row.get("value_as_number") not in (None, "")]
    if not numeric:
        return {"value": None, "reason": "no_numeric_value"}
    units = {str(row.get("unit_concept_id") or "0") for row in numeric}
    if "0" in units and not dimensionless:
        return {"value": None, "reason": "unknown_unit"}
    if len(units) > 1:
        return {"value": None, "reason": "unit_conflict"}
    values = [float(row["value_as_number"]) for row in numeric]
    if not all(isfinite(value) for value in values):
        return {"value": None, "reason": "nonfinite_value"}
    return {"value": mean(values), "reason": "ok"}


def numeric_summary(values):
    values = list(values)
    numbers = sorted(float(value) for value in values if value not in (None, "") and isfinite(float(value)))
    def quantile(q):
        if not numbers:
            return None
        position = (len(numbers) - 1) * q
        low = int(position)
        return numbers[low] + (numbers[min(low + 1, len(numbers) - 1)] - numbers[low]) * (position - low)
    q1, q3 = quantile(.25), quantile(.75)
    return {"n": len(numbers), "missing": len(values) - len(numbers), "mean": mean(numbers) if numbers else None,
            "sd": stdev(numbers) if len(numbers) > 1 else None, "min": numbers[0] if numbers else None,
            "q1": q1, "median": quantile(.5), "q3": q3, "iqr": q3 - q1 if numbers else None,
            "max": numbers[-1] if numbers else None, "quantile_method": "linear (n-1)"}


def ensure_disjoint_partitions(partitions):
    assigned = set()
    for people in partitions.values():
        people = set(people)
        if assigned.intersection(people):
            raise ValueError("A person occurs in more than one declared study partition")
        assigned.update(people)
