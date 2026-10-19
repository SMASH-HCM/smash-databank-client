import pytest

from smash_hcm_databank_client.database import OmopDatabase, sha256
from smash_hcm_databank_client.reports import inventory, overlap
from smash_hcm_databank_client.validation import validate_database

pytestmark = pytest.mark.integration


def test_external_database_integrity_and_read_only(external_db_path):
    # Missing explicit paths fail, rather than silently skipping a requested release.
    before = sha256(external_db_path)
    with OmopDatabase(external_db_path) as database:
        result = validate_database(database)
        assert result["status"] == "PASS"
        assert result["database_sha256"] == before
        assert database.count("person") > 0
    assert sha256(external_db_path) == before


def test_external_inventory_and_overlap_reconcile(external_db_path):
    with OmopDatabase(external_db_path) as database:
        result = inventory(database)
        assert sum(result["patients_by_site"].values()) == database.count("person")
        shared = overlap(database)
        assert shared["core_count"] == len(shared["core"])
        assert shared["two_site_count"] == sum(shared["two_site_counts"].values())
        assert all(len(row["sites"]) == 3 for row in shared["core"])
        assert all(len(row["sites"]) == 2 for row in shared["two_site"])
        # Counts are intentionally not tied to a future v1.4 release.
