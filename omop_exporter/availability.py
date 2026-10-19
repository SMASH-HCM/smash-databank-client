"""Versioned post-assessment/pre-intervention feature availability mask.

The requested protocol accepts prediction-day measurements, but RC4 has no
general intraday/source-role ledger. Unclassified same-day facts are held out;
their absence is never treated as proof that they are therapeutic actions.
"""

POLICIES = ("post-assessment", "strict-before")
DIAGNOSTIC_PROCEDURES = {37311810, 4065278, 4082987, 4163951, 4230911, 42710007}
CLINICAL_OBSERVATIONS = {3966183, 4213477, 4013886, 4135376, 44803968, 4307028, 46270007, 21491926, 4223659, 4145764, 4307859, 4311963}
OUTCOME_OR_DECISION_OBSERVATIONS = {4083743, 4178679, 4306655, 4156363, 2000001101}


def held_reason(table, concept, name, same_day, policy):
    if policy == "strict-before":
        return "same_day_excluded_by_strict_boundary" if same_day else ""
    if policy != "post-assessment":
        raise ValueError("Unknown availability policy")
    label = str(name).casefold()
    if (table == "observation" and concept in OUTCOME_OR_DECISION_OBSERVATIONS) or label.startswith(("smash cohort membership:", "smash follow-up", "smash endpoint")):
        return "administrative_outcome_or_decision_derived"
    if not same_day:
        return ""
    if table == "measurement":
        return ""
    if table == "procedure_occurrence" and concept in DIAGNOSTIC_PROCEDURES:
        return ""
    if table == "observation" and concept in CLINICAL_OBSERVATIONS:
        return ""
    return "same_day_role_unreviewed_or_therapeutic"


def policy_document(policy):
    if policy not in POLICIES:
        raise ValueError("Unknown availability policy")
    return {"policy": policy, "version": policy + "-v1", "lookahead": "No observations after the baseline date",
            "prediction_time": "after available diagnostic assessment, before new treatment decisions" if policy == "post-assessment" else "strictly before the baseline date",
            "same_day_measurements": policy == "post-assessment",
            "same_day_diagnostic_procedure_ids": sorted(DIAGNOSTIC_PROCEDURES) if policy == "post-assessment" else [],
            "same_day_clinical_observation_ids": sorted(CLINICAL_OBSERVATIONS) if policy == "post-assessment" else [],
            "held_out_observation_ids_at_any_time": sorted(OUTCOME_OR_DECISION_OBSERVATIONS) if policy == "post-assessment" else [],
            "unclassified_same_day_facts": "held out, including unclassified condition, drug, device and procedure records",
            "medication_history": "Earlier history may remain; generic 3021806 is still held for unresolved class context",
            "limitation": "Initial conservative concept-role mask, not complete intraday/source-level availability. A new decision versus established therapy cannot always be identified from RC4.",
            "strict_before_scope": "Historical boundary control; strict timing alone is not an administrative/outcome leakage mask"}
