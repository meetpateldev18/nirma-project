"""
Unit Test Suite for Nirma University Roll Number Taxonomy Parser.

Validates:
1. Parsing of standard undergraduate roll numbers ('21BCE045', '23BAI012').
2. Parsing of postgraduate and professional programs ('22MBA104', '24MCA015', '22BPH030').
3. Case-insensitivity and whitespace stripping.
4. Correct email generation ('21bce045@nirmauni.ac.in').
5. Failure modes on invalid lengths, symbols, and non-existent branch codes.
"""

import pytest
from backend.utils.roll_parser import parse_nirma_roll


def test_valid_btech_cse_roll():
    """Tests parsing of typical B.Tech CSE roll number."""
    result = parse_nirma_roll("21BCE045")
    assert result.is_valid is True
    assert result.admission_year == 2021
    assert result.program_code == "BCE"
    assert result.student_serial == 45
    assert result.official_email == "21bce045@nirmauni.ac.in"
    assert result.institute_code == "ITNU"
    assert result.department_code == "CSE"
    assert result.program_level == "UG"


def test_valid_mba_roll_case_insensitive():
    """Tests lower-case and whitespace handling for MBA roll."""
    result = parse_nirma_roll("  22mba104  ")
    assert result.is_valid is True
    assert result.admission_year == 2022
    assert result.program_code == "MBA"
    assert result.student_serial == 104
    assert result.official_email == "22mba104@nirmauni.ac.in"
    assert result.institute_code == "IMNU"
    assert result.department_code == "DMS"
    assert result.program_level == "PG"


def test_valid_pharmacy_and_law():
    """Tests B.Pharm and Law roll numbers."""
    bph = parse_nirma_roll("23BPH019")
    assert bph.is_valid is True
    assert bph.institute_code == "IPNU"

    bal = parse_nirma_roll("24BAL088")
    assert bal.is_valid is True
    assert bal.institute_code == "ILNU"


def test_invalid_length_and_symbols():
    """Tests invalid formatting rejects gracefully with diagnostic message."""
    short = parse_nirma_roll("21BCE45")
    assert short.is_valid is False
    assert "8-character format" in short.error_message

    symbols = parse_nirma_roll("21BCE04!")
    assert symbols.is_valid is False

    unknown_branch = parse_nirma_roll("21XYZ001")
    assert unknown_branch.is_valid is False
    assert "Unknown program/branch code" in unknown_branch.error_message
