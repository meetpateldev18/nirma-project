"""
Unit test suite for in-memory Student Trie search engine.
"""

import pytest

from backend.database.models import StaffUser
from backend.services.student_trie import StudentSearchDTO, StudentTrie


@pytest.fixture
def populated_trie() -> StudentTrie:
    """Fixture returning a pre-populated in-memory student Trie."""
    trie = StudentTrie()
    s1 = StudentSearchDTO(
        id=1,
        name="Gandhi Urva Yogeshkumar",
        roll_number="23BCE078",
        phone="+918866241204",
        department="Computer Science & Engineering",
        department_id=1,
        institute_id=1,
    )
    s2 = StudentSearchDTO(
        id=2,
        name="Aarav Patel",
        roll_number="21BCE001",
        phone="+919876500001",
        department="Computer Science & Engineering",
        department_id=1,
        institute_id=1,
    )
    s3 = StudentSearchDTO(
        id=3,
        name="Pooja Sharma",
        roll_number="21BCE002",
        phone="+919876500002",
        department="Computer Science & Engineering",
        department_id=1,
        institute_id=1,
    )
    s4 = StudentSearchDTO(
        id=4,
        name="Rohan Mehta",
        roll_number="21BME003",
        phone="+919876500003",
        department="Mechanical Engineering",
        department_id=2,
        institute_id=1,
    )
    trie.insert_student(s1)
    trie.insert_student(s2)
    trie.insert_student(s3)
    trie.insert_student(s4)
    trie._is_loaded = True
    return trie


def test_trie_search_single_character(populated_trie: StudentTrie):
    """Verifies that 1 character immediately returns matching students."""
    admin = StaffUser(id=1, email="admin@nirmauni.ac.in", role="admin")
    results = populated_trie.search("A", admin)
    assert len(results) >= 1
    assert any(r["name"] == "Aarav Patel" for r in results)


def test_trie_search_surname(populated_trie: StudentTrie):
    """Verifies that searching by surname (e.g. 'Patel' or 'Sharma') matches properly."""
    admin = StaffUser(id=1, email="admin@nirmauni.ac.in", role="admin")
    results_patel = populated_trie.search("Patel", admin)
    assert len(results_patel) == 1
    assert results_patel[0]["name"] == "Aarav Patel"

    results_sharma = populated_trie.search("Sharma", admin)
    assert len(results_sharma) == 1
    assert results_sharma[0]["name"] == "Pooja Sharma"


def test_trie_search_roll_number(populated_trie: StudentTrie):
    """Verifies roll number search with prefix or suffix."""
    admin = StaffUser(id=1, email="admin@nirmauni.ac.in", role="admin")
    results = populated_trie.search("21BME", admin)
    assert len(results) == 1
    assert results[0]["roll_number"] == "21BME003"


def test_trie_abac_operator_scoping(populated_trie: StudentTrie):
    """Verifies that operators only see students in their assigned department."""
    cse_operator = StaffUser(
        id=2,
        email="operator@nirmauni.ac.in",
        role="operator",
        department_id=1,
        institute_id=1,
    )
    # Searching 'Rohan' (Mechanical) should return nothing for CSE operator
    me_results = populated_trie.search("Rohan", cse_operator)
    assert len(me_results) == 0

    # Searching 'Aarav' (CSE) should return results
    cse_results = populated_trie.search("Aarav", cse_operator)
    assert len(cse_results) == 1
    assert cse_results[0]["name"] == "Aarav Patel"


def test_trie_search_in_between_substring(populated_trie: StudentTrie):
    """Verifies that in-between substring queries match students (e.g., 'atel' -> 'Aarav Patel')."""
    admin = StaffUser(id=1, email="admin@nirmauni.ac.in", role="admin")
    results = populated_trie.search("atel", admin)
    assert len(results) >= 1
    assert any(r["name"] == "Aarav Patel" for r in results)

    results_mehta = populated_trie.search("ehta", admin)
    assert len(results_mehta) >= 1
    assert any(r["name"] == "Rohan Mehta" for r in results_mehta)


def test_trie_search_roll_suffix(populated_trie: StudentTrie):
    """Verifies that roll number suffixes match (e.g., '078', '002', 'BCE')."""
    admin = StaffUser(id=1, email="admin@nirmauni.ac.in", role="admin")
    results_078 = populated_trie.search("078", admin)
    assert len(results_078) >= 1
    assert any(r["roll_number"] == "23BCE078" for r in results_078)

    results_bce = populated_trie.search("bce", admin)
    assert len(results_bce) == 3


def test_trie_search_multiple_tokens(populated_trie: StudentTrie):
    """Verifies that multiple words in query match regardless of token order (Surname First or Given Name First)."""
    admin = StaffUser(id=1, email="admin@nirmauni.ac.in", role="admin")
    results1 = populated_trie.search("Urva Gandhi", admin)
    assert len(results1) == 1
    assert results1[0]["name"] == "Gandhi Urva Yogeshkumar"

    results2 = populated_trie.search("Gandhi Urva", admin)
    assert len(results2) == 1
    assert results2[0]["name"] == "Gandhi Urva Yogeshkumar"


def test_trie_search_adversarial_and_empty_queries(populated_trie: StudentTrie):
    """Verifies that empty strings, whitespace, or pure special characters return gracefully."""
    admin = StaffUser(id=1, email="admin@nirmauni.ac.in", role="admin")
    assert populated_trie.search("", admin) == []
    assert populated_trie.search("   ", admin) == []
    assert populated_trie.search("!@#$%^&*()", admin) == []
