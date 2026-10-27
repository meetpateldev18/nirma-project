"""
Nirma University Roll Number Taxonomy Parser & Validator Utility.

Enforces the official Nirma University 8-character roll number standard:
    [Admission Year (2 Digits)] + [Program/Branch Code (3 Letters)] + [Serial Index (3 Digits)]
    Example: '21BCE045', '23BAI012', '22MBA104'

Provides deterministic attribute extraction for automated ERP/SIS student
roster imports, validating branch codes and deriving official email domains.

Dependencies:
    - python >= 3.11
"""

import re
from typing import Any, Dict, Optional

# Alphanumeric 8-character regex matching official Nirma roll taxonomy
NIRMA_ROLL_REGEX = re.compile(
    r"^(?P<year>\d{2})(?P<branch>[A-Z]{3})(?P<index>\d{3})$",
    re.IGNORECASE,
)

# Canonical Registry of Nirma University Branch Roll Codes
OFFICIAL_BRANCH_CODES: Dict[str, Dict[str, str]] = {
    # Institute of Technology (ITNU)
    "BCE": {"institute": "ITNU", "dept": "CSE", "level": "UG", "name": "B.Tech in Computer Science & Engineering"},
    "BAI": {"institute": "ITNU", "dept": "CSE", "level": "UG", "name": "B.Tech in CSE (Artificial Intelligence & ML)"},
    "BIT": {"institute": "ITNU", "dept": "CSE", "level": "UG", "name": "B.Tech in Information Technology"},
    "BEC": {"institute": "ITNU", "dept": "ECE", "level": "UG", "name": "B.Tech in Electronics & Communication Engineering"},
    "BEE": {"institute": "ITNU", "dept": "EE", "level": "UG", "name": "B.Tech in Electrical Engineering"},
    "BME": {"institute": "ITNU", "dept": "ME", "level": "UG", "name": "B.Tech in Mechanical Engineering"},
    "BCL": {"institute": "ITNU", "dept": "CL", "level": "UG", "name": "B.Tech in Civil Engineering"},
    "BCH": {"institute": "ITNU", "dept": "CH", "level": "UG", "name": "B.Tech in Chemical Engineering"},
    "BIC": {"institute": "ITNU", "dept": "IC", "level": "UG", "name": "B.Tech in Instrumentation & Control Engineering"},
    "MCE": {"institute": "ITNU", "dept": "CSE", "level": "PG", "name": "M.Tech in Computer Science & Engineering"},
    "MVL": {"institute": "ITNU", "dept": "ECE", "level": "PG", "name": "M.Tech in VLSI Design"},
    "MEP": {"institute": "ITNU", "dept": "EE", "level": "PG", "name": "M.Tech in Electrical Power Systems"},
    "MME": {"institute": "ITNU", "dept": "ME", "level": "PG", "name": "M.Tech in Mechanical Engineering (CAD/CAM)"},
    "MCL": {"institute": "ITNU", "dept": "CL", "level": "PG", "name": "M.Tech in Construction Technology & Management"},
    "MCA": {"institute": "ITNU", "dept": "CSE", "level": "PG", "name": "Master of Computer Applications"},

    # Institute of Management (IMNU)
    "MBA": {"institute": "IMNU", "dept": "DMS", "level": "PG", "name": "Master of Business Administration"},
    "IBM": {"institute": "IMNU", "dept": "DMS", "level": "INTEGRATED", "name": "Integrated BBA-MBA (5-Year Program)"},
    "BBA": {"institute": "IMNU", "dept": "DMS", "level": "UG", "name": "Bachelor of Business Administration (Hons)"},

    # Institute of Pharmacy (IPNU)
    "BPH": {"institute": "IPNU", "dept": "DPS", "level": "UG", "name": "Bachelor of Pharmacy (B.Pharm)"},
    "MPH": {"institute": "IPNU", "dept": "DPS", "level": "PG", "name": "Master of Pharmacy (M.Pharm)"},

    # Institute of Science (ISNU)
    "MBT": {"institute": "ISNU", "dept": "DBS", "level": "PG", "name": "M.Sc. in Biotechnology"},
    "MMB": {"institute": "ISNU", "dept": "DBS", "level": "PG", "name": "M.Sc. in Microbiology"},
    "MBC": {"institute": "ISNU", "dept": "DBS", "level": "PG", "name": "M.Sc. in Biochemistry"},
    "MCH": {"institute": "ISNU", "dept": "DCH", "level": "PG", "name": "M.Sc. in Chemistry"},

    # Institute of Law (ILNU)
    "BAL": {"institute": "ILNU", "dept": "DOL", "level": "UG", "name": "B.A. LL.B. (Hons)"},
    "BBL": {"institute": "ILNU", "dept": "DOL", "level": "UG", "name": "B.B.A. LL.B. (Hons)"},
    "LLM": {"institute": "ILNU", "dept": "DOL", "level": "PG", "name": "Master of Laws (LL.M.)"},

    # Institute of Architecture & Planning (IAPNU)
    "BAR": {"institute": "IAPNU", "dept": "DOA", "level": "UG", "name": "Bachelor of Architecture (B.Arch)"},
    "BPL": {"institute": "IAPNU", "dept": "DOP", "level": "UG", "name": "Bachelor of Planning (B.Plan)"},

    # Institute of Commerce (ICNU)
    "BCM": {"institute": "ICNU", "dept": "DOC", "level": "UG", "name": "Bachelor of Commerce (B.Com Hons)"},

    # Institute of Design (IDNU)
    "BCD": {"institute": "IDNU", "dept": "DOD", "level": "UG", "name": "B.Des in Communication Design"},
    "BID": {"institute": "IDNU", "dept": "DOD", "level": "UG", "name": "B.Des in Industrial Design"},

    # Central Doctoral Studies (FDSR)
    "PHD": {"institute": "FDSR", "dept": "FDSR", "level": "DOCTORAL", "name": "Doctor of Philosophy (Ph.D.)"},
}


class RollParseResult:
    """Structured DTO encapsulating decomposed roll number attributes."""

    def __init__(
        self,
        raw_roll: str,
        is_valid: bool,
        admission_year: Optional[int] = None,
        program_code: Optional[str] = None,
        student_serial: Optional[int] = None,
        official_email: Optional[str] = None,
        institute_code: Optional[str] = None,
        department_code: Optional[str] = None,
        program_name: Optional[str] = None,
        program_level: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        self.raw_roll = raw_roll
        self.is_valid = is_valid
        self.admission_year = admission_year
        self.program_code = program_code
        self.student_serial = student_serial
        self.official_email = official_email
        self.institute_code = institute_code
        self.department_code = department_code
        self.program_name = program_name
        self.program_level = program_level
        self.error_message = error_message

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the result to a dictionary."""
        return {
            "raw_roll": self.raw_roll,
            "is_valid": self.is_valid,
            "admission_year": self.admission_year,
            "program_code": self.program_code,
            "student_serial": self.student_serial,
            "official_email": self.official_email,
            "institute_code": self.institute_code,
            "department_code": self.department_code,
            "program_name": self.program_name,
            "program_level": self.program_level,
            "error_message": self.error_message,
        }


def parse_nirma_roll(roll_number: str) -> RollParseResult:
    """
    Parses and validates an 8-character Nirma University student roll number.

    Args:
        roll_number: The student roll string (e.g. '21BCE045', '23bai012').

    Returns:
        RollParseResult containing parsed year, program code, serial, and mapped branch.
    """
    cleaned = roll_number.strip().upper()
    match = NIRMA_ROLL_REGEX.match(cleaned)
    if not match:
        return RollParseResult(
            raw_roll=roll_number,
            is_valid=False,
            error_message=f"Roll number '{roll_number}' does not match standard 8-character format (e.g. 21BCE045).",
        )

    groups = match.groupdict()
    year_prefix = int(groups["year"])
    admission_year = 2000 + year_prefix
    branch_code = groups["branch"]
    serial_idx = int(groups["index"])
    official_email = f"{cleaned.lower()}@nirmauni.ac.in"

    branch_meta = OFFICIAL_BRANCH_CODES.get(branch_code)
    if not branch_meta:
        return RollParseResult(
            raw_roll=cleaned,
            is_valid=False,
            admission_year=admission_year,
            program_code=branch_code,
            student_serial=serial_idx,
            official_email=official_email,
            error_message=f"Unknown program/branch code '{branch_code}' in Nirma taxonomy.",
        )

    return RollParseResult(
        raw_roll=cleaned,
        is_valid=True,
        admission_year=admission_year,
        program_code=branch_code,
        student_serial=serial_idx,
        official_email=official_email,
        institute_code=branch_meta["institute"],
        department_code=branch_meta["dept"],
        program_name=branch_meta["name"],
        program_level=branch_meta["level"],
    )
