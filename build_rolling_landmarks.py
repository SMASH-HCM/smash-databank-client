"""Create endpoint-specific rolling training and fixed baseline evaluation rows.

Uses the provisional source-derived manifest/horizon labels. The ETL endpoint
ledger can replace these inputs without changing the downstream row contract.
No future endpoint is used to choose a landmark; training landmarks are the
baseline and annual anniversaries while the person remains at risk.
"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


HORIZONS = (1, 2, 5)
YEAR_DAYS = 365.2425


def read_rows(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        yield from csv.DictReader(handle)


def parse_date(value):
    return date.fromisoformat(value[:10]) if value else None


def anniversary(start, years):
    try:
        return start.replace(year=start.year + years)
    except ValueError:  # 29 February
        return start.replace(year=start.year + years, day=28)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, help="Defaults to --data-dir")
    parser.add_argument("--max-training-years", type=int, default=5)
    parser.add_argument("--followup-gap-policy", choices=("exclude", "observed-event"), default="observed-event",
                        help="Treatment of dated endpoints after recorded clinical follow-up")
    args = parser.parse_args()
    output_dir = args.output_dir or args.data_dir
    if args.max_training_years < 0:
        parser.error("--max-training-years must be nonnegative")
    people = {r["person_id"]: r for r in read_rows(args.data_dir / "patient_manifest.csv")}
    initial = {}
    for row in read_rows(args.data_dir / "horizon_labels.csv"):
        if row["horizon_years"] == "1":
            initial[(row["person_id"], row["endpoint"])] = row
    audit = Counter()
    landmarks = []
    horizons = []
    for (pid, endpoint), source in sorted(initial.items()):
        person = people[pid]
        split = person["split"]
        site = person["site"]
        anchor = parse_date(person["index_date"])
        censor = parse_date(person["censor_date"])
        event = parse_date(source["event_date"])
        reason = ""
        if site == "TAMPERE":
            reason = "unsupported_endpoint"
        elif source["cohort_status_conflict"] == "1":
            reason = "cohort_status_conflict"
        elif not anchor or not person["baseline_age_years"]:
            reason = "missing_anchor_or_age"
        elif source["label_reason"] == "positive_without_event_date":
            reason = "positive_without_event_date"
        elif event and event <= anchor:
            reason = "prevalent_or_same_day_event"
        elif event and (not censor or event > censor) and args.followup_gap_policy == "exclude":
            reason = "event_after_recorded_followup"
        elif not event and (not censor or censor <= anchor):
            reason = "no_post_baseline_followup"
        if reason:
            audit[f"excluded_{site}_{endpoint}_{reason}"] += 1
            continue

        # A dated endpoint establishes its event time even when it follows the
        # last clinic visit. The unresolved interval remains flagged for ETL
        # review; --followup-gap-policy exclude is a sensitivity analysis.
        endpoint_end = event if event else censor
        candidates = [anchor]
        if split.endswith("-TRAIN"):
            candidates += [anniversary(anchor, y) for y in range(1, args.max_training_years + 1)]
        valid_candidates = [d for d in candidates if d < endpoint_end]
        if not valid_candidates:
            audit[f"excluded_{site}_{endpoint}_no_at_risk_landmark"] += 1
            continue
        for n, landmark in enumerate(valid_candidates):
            duration_days = (endpoint_end - landmark).days
            if duration_days <= 0:
                raise AssertionError("Survival duration must be positive")
            observed = int(event is not None)
            age = float(person["baseline_age_years"]) + (landmark - anchor).days / YEAR_DAYS
            landmark_id = f"{pid}:{endpoint}:{n}"
            record = {
                "landmark_id": landmark_id, "person_id": pid, "site": site, "split": split,
                "endpoint": endpoint, "landmark_date": landmark.isoformat(),
                "landmark_age_years": f"{age:.8f}",
                "years_since_anchor": f"{(landmark - anchor).days / YEAR_DAYS:.8f}",
                "time_to_event_or_censor_days": duration_days,
                "event_observed": observed,
                "event_date": event.isoformat() if event else "",
                "censor_date": censor.isoformat() if censor else "",
                "event_after_recorded_followup": int(bool(event and (not censor or event > censor))),
                "sample_weight": f"{1 / len(valid_candidates):.8f}",
                "landmark_policy": "annual_train" if split.endswith("-TRAIN") else "fixed_baseline",
            }
            landmarks.append(record)
            audit[f"included_{split}_{endpoint}_landmarks"] += 1
            if observed:
                audit[f"included_{split}_{endpoint}_event_rows"] += 1
            for horizon in HORIZONS:
                horizon_days = round(YEAR_DAYS * horizon)
                if observed and duration_days <= horizon_days:
                    label, reason_h = 1, "event_in_horizon"
                elif duration_days >= horizon_days:
                    label, reason_h = 0, "observed_event_free_to_horizon"
                else:
                    label, reason_h = "", "censored_before_horizon"
                horizons.append({"landmark_id": landmark_id, "person_id": pid,
                                 "site": site, "split": split, "endpoint": endpoint,
                                 "horizon_years": horizon, "label": label,
                                 "label_reason": reason_h,
                                 "event_after_recorded_followup": record["event_after_recorded_followup"]})
                audit[f"horizon_{split}_{endpoint}_{horizon}_{reason_h}"] += 1
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, records in (("landmarks.csv", landmarks), ("landmark_horizon_labels.csv", horizons)):
        if not records:
            raise ValueError(f"No rows for {filename}")
        with (output_dir / filename).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    (output_dir / "landmark_audit.json").write_text(
        json.dumps({"policy": {"max_training_years": args.max_training_years,
                                "followup_gap_policy": args.followup_gap_policy},
                    "counts": dict(sorted(audit.items()))}, indent=2) + "\n", encoding="utf-8")
    print(f"Landmarks: {len(landmarks)}; horizon labels: {len(horizons)}")
    print(f"Excluded patient-endpoints: {sum(v for k, v in audit.items() if k.startswith('excluded_'))}")


if __name__ == "__main__":
    main()
