"""Automated tests for the reusable library and desktop file operations."""

from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app import read_csv_file, read_rule_file, write_validation_report
from datasure_core import (
    ConfigurationError,
    EmailRule,
    IntegerRule,
    RangeRule,
    RequiredRule,
    RuleFactory,
    UniqueRule,
    ValidationIssue,
    ValidationReport,
    ValidatorEngine,
)


class RequiredRuleTests(unittest.TestCase):
    def test_rejects_empty_value(self) -> None:
        self.assertIsNotNone(RequiredRule().validate("", {}))

    def test_rejects_whitespace(self) -> None:
        self.assertIsNotNone(RequiredRule().validate("   ", {}))

    def test_accepts_text(self) -> None:
        self.assertIsNone(RequiredRule().validate("Alice", {}))


class IntegerRuleTests(unittest.TestCase):
    def test_accepts_whole_number(self) -> None:
        self.assertIsNone(IntegerRule().validate("-12", {}))

    def test_rejects_text(self) -> None:
        self.assertIsNotNone(IntegerRule().validate("twelve", {}))

    def test_rejects_decimal(self) -> None:
        self.assertIsNotNone(IntegerRule().validate("12.5", {}))


class RangeRuleTests(unittest.TestCase):
    def test_accepts_both_boundaries(self) -> None:
        rule = RangeRule(minimum=18, maximum=100)
        self.assertIsNone(rule.validate("18", {}))
        self.assertIsNone(rule.validate("100", {}))

    def test_rejects_value_below_minimum(self) -> None:
        self.assertIsNotNone(RangeRule(minimum=18).validate("17", {}))

    def test_rejects_non_numeric_value(self) -> None:
        self.assertIsNotNone(RangeRule(maximum=100).validate("twenty", {}))

    def test_rejects_reversed_boundaries(self) -> None:
        with self.assertRaises(ConfigurationError):
            RangeRule(minimum=10, maximum=5)


class EmailAndUniqueRuleTests(unittest.TestCase):
    def test_email_accepts_normal_address(self) -> None:
        self.assertIsNone(EmailRule().validate("alice@example.com", {}))

    def test_email_rejects_invalid_address(self) -> None:
        self.assertIsNotNone(EmailRule().validate("invalid-email", {}))

    def test_unique_rejects_duplicate(self) -> None:
        from collections import Counter

        context = {"value_counts": Counter(("1001", "1001", "1002"))}
        self.assertIsNotNone(UniqueRule().validate("1001", context))
        self.assertIsNone(UniqueRule().validate("1002", context))


class RuleFactoryTests(unittest.TestCase):
    def test_creates_every_supported_rule(self) -> None:
        cases = (
            ({"type": "required"}, RequiredRule),
            ({"type": "integer"}, IntegerRule),
            ({"type": "email"}, EmailRule),
            ({"type": "unique"}, UniqueRule),
            ({"type": "range", "minimum": 1}, RangeRule),
        )
        for specification, expected_type in cases:
            with self.subTest(specification=specification):
                self.assertIsInstance(RuleFactory.create(specification), expected_type)

    def test_rejects_unknown_rule(self) -> None:
        with self.assertRaises(ConfigurationError):
            RuleFactory.create({"type": "unknown"})

    def test_rejects_non_numeric_range_parameter(self) -> None:
        with self.assertRaises(ConfigurationError):
            RuleFactory.create({"type": "range", "minimum": "young"})


class ValidatorEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = ValidatorEngine()
        self.rows = [
            {"name": "Alice", "age": "21"},
            {"name": "", "age": "17"},
        ]
        self.configuration = {
            "name": [{"type": "required"}],
            "age": [{"type": "integer"}, {"type": "range", "minimum": 18}],
        }

    def test_reports_physical_row_and_column(self) -> None:
        report = self.engine.validate(self.rows, self.configuration)
        self.assertIn(
            (3, "name"), {(issue.row, issue.column) for issue in report.issues}
        )

    def test_calculates_summary(self) -> None:
        report = self.engine.validate(self.rows, self.configuration)
        self.assertEqual(report.total_rows, 2)
        self.assertEqual(report.valid_rows, 1)
        self.assertEqual(report.invalid_rows, 1)
        self.assertFalse(report.passed)

    def test_rejects_missing_configured_column(self) -> None:
        with self.assertRaises(ConfigurationError):
            self.engine.validate(self.rows, {"email": [{"type": "email"}]})

    def test_does_not_modify_input_rows(self) -> None:
        original = copy.deepcopy(self.rows)
        self.engine.validate(self.rows, self.configuration)
        self.assertEqual(self.rows, original)

    def test_valid_rows_produce_no_issues(self) -> None:
        report = self.engine.validate(
            [{"name": "Alice", "age": "21"}], self.configuration
        )
        self.assertTrue(report.passed)
        self.assertEqual(report.issue_count, 0)

    def test_empty_csv_can_be_checked_using_explicit_columns(self) -> None:
        report = self.engine.validate(
            [], self.configuration, columns=("name", "age")
        )
        self.assertTrue(report.passed)
        self.assertEqual(report.total_rows, 0)


class FileOperationTests(unittest.TestCase):
    def test_supplied_sample_produces_expected_summary(self) -> None:
        project = Path(__file__).parent
        columns, rows = read_csv_file(project / "sample_students.csv")
        rules = read_rule_file(project / "validation_rules.json")
        report = ValidatorEngine().validate(rows, rules, columns=columns)
        self.assertEqual(report.total_rows, 4)
        self.assertEqual(report.valid_rows, 1)
        self.assertEqual(report.invalid_rows, 3)
        self.assertEqual(report.issue_count, 7)

    def test_rejects_csv_with_duplicate_headers(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("name,name\nAlice,Bob\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_csv_file(path)

    def test_rejects_json_array_as_configuration(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps([{"type": "required"}]), encoding="utf-8")
            with self.assertRaises(ValueError):
                read_rule_file(path)

    def test_exports_report_with_expected_columns(self) -> None:
        report = ValidationReport(
            total_rows=1,
            issues=(
                ValidationIssue(
                    row=2,
                    column="name",
                    value="",
                    rule="required",
                    message="Value is required.",
                ),
            ),
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "report.csv"
            write_validation_report(path, report)
            with path.open(newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(list(rows[0]), ["row", "column", "value", "rule", "message"])
            self.assertEqual(rows[0]["column"], "name")


if __name__ == "__main__":
    unittest.main()
