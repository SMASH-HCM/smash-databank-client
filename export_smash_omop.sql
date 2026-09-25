-- Run inside an isolated restore of SMASH_v1.2_cardiac_db.dump.
-- /out must be an ignored, access-controlled patient-data directory.
-- Cohort dates in this release are import dates, not clinical event dates.

COPY (
    SELECT p.person_id, p.person_source_value, p.gender_concept_id,
           p.race_concept_id, p.ethnicity_concept_id
    FROM cdm.person AS p
    ORDER BY p.person_id
) TO '/out/person.csv' WITH (FORMAT CSV, HEADER TRUE);

COPY (
    SELECT c.subject_id AS person_id, c.cohort_definition_id
    FROM results.cohort AS c
    WHERE c.cohort_definition_id BETWEEN 1000 AND 1410
    ORDER BY c.subject_id, c.cohort_definition_id
) TO '/out/cohort_membership.csv' WITH (FORMAT CSV, HEADER TRUE);

COPY (
    SELECT person_id, observation_period_start_date, observation_period_end_date
    FROM cdm.observation_period
    ORDER BY person_id, observation_period_start_date
) TO '/out/observation_period.csv' WITH (FORMAT CSV, HEADER TRUE);

COPY (
    SELECT person_id, death_date, death_type_concept_id
    FROM cdm.death
    ORDER BY person_id, death_date
) TO '/out/death.csv' WITH (FORMAT CSV, HEADER TRUE);

-- This is a dated event stream, not a model feature matrix. The landmark
-- builder must filter to events available at or before its index time.
-- Exclude release-management observations (SMASH:*) dated at import time.
COPY (
    SELECT person_id, 'condition'::text AS domain,
           condition_concept_id AS concept_id,
           condition_start_date AS event_date,
           NULL::numeric AS value_as_number,
           NULL::integer AS value_as_concept_id,
           NULL::integer AS unit_concept_id
    FROM cdm.condition_occurrence
    UNION ALL
    SELECT person_id, 'measurement', measurement_concept_id,
           measurement_date, value_as_number, value_as_concept_id,
           unit_concept_id
    FROM cdm.measurement
    UNION ALL
    SELECT person_id, 'observation', observation_concept_id,
           observation_date, value_as_number, value_as_concept_id,
           unit_concept_id
    FROM cdm.observation
    WHERE observation_source_value IS DISTINCT FROM 'SMASH:__registry__:present'
      AND (observation_source_value IS NULL OR observation_source_value NOT LIKE 'SMASH:%')
    UNION ALL
    SELECT person_id, 'procedure', procedure_concept_id,
           procedure_date, NULL::numeric, NULL::integer, NULL::integer
    FROM cdm.procedure_occurrence
    UNION ALL
    SELECT person_id, 'drug', drug_concept_id,
           drug_exposure_start_date, NULL::numeric, NULL::integer, NULL::integer
    FROM cdm.drug_exposure
    ORDER BY person_id, event_date, domain, concept_id
) TO '/out/omop_events.csv' WITH (FORMAT CSV, HEADER TRUE);
