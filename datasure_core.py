"""Reusable, user-interface-independent validation library for DataSure.

The public API intentionally accepts ordinary Python mappings and returns
dataclasses.  It does not import Tkinter or perform file input/output, so it can
be reused by desktop, command-line, or web applications.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Any, ClassVar


class ConfigurationError(ValueError):
    """Raised when a validation configuration cannot be used safely."""


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One failed validation result."""

    row: int
    column: str
    value: str
    rule: str
    message: str

    def as_dict(self) -> dict[str, str | int]:
        """Return a representation suitable for CSV or JSON export."""

        return {
            "row": self.row,
            "column": self.column,
            "value": self.value,
            "rule": self.rule,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Summary and detailed issues produced by a validation run."""

    total_rows: int
    issues: tuple[ValidationIssue, ...]

    @property
    def issue_count(self) -> int:
        """Return the total number of rule failures."""

        return len(self.issues)

    @property
    def invalid_rows(self) -> int:
        """Return the number of data rows containing at least one issue."""

        return len({issue.row for issue in self.issues})

    @property
    def valid_rows(self) -> int:
        """Return the number of data rows with no reported issue."""

        return self.total_rows - self.invalid_rows

    @property
    def passed(self) -> bool:
        """Return True when no issues were found."""

        return not self.issues


class ValidationRule(ABC):
    """Strategy interface implemented by every validation rule."""

    rule_type: ClassVar[str] = "base"

    @abstractmethod
    def validate(self, value: str, context: Mapping[str, Any]) -> str | None:
        """Return an error message for invalid data, otherwise return None."""


class RequiredRule(ValidationRule):
    """Require a non-empty value."""

    rule_type = "required"

    def validate(self, value: str, context: Mapping[str, Any]) -> str | None:
        del context
        if not _normalise(value):
            return "Value is required."
        return None


class IntegerRule(ValidationRule):
    """Require a whole-number value when a value is present."""

    rule_type = "integer"
    _integer_pattern = re.compile(r"[+-]?\d+")

    def validate(self, value: str, context: Mapping[str, Any]) -> str | None:
        del context
        text = _normalise(value)
        if not text:
            return None
        if self._integer_pattern.fullmatch(text) is None:
            return "Value must be an integer."
        return None


class RangeRule(ValidationRule):
    """Require a numeric value to fall within an inclusive range."""

    rule_type = "range"

    def __init__(
        self,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> None:
        if minimum is None and maximum is None:
            raise ConfigurationError(
                "A range rule requires 'minimum', 'maximum', or both."
            )
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ConfigurationError("Range minimum cannot exceed maximum.")
        self.minimum = minimum
        self.maximum = maximum

    def validate(self, value: str, context: Mapping[str, Any]) -> str | None:
        del context
        text = _normalise(value)
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return "Value must be numeric."

        if self.minimum is not None and number < self.minimum:
            return f"Value must be at least {self.minimum:g}."
        if self.maximum is not None and number > self.maximum:
            return f"Value must be at most {self.maximum:g}."
        return None


class EmailRule(ValidationRule):
    """Check a practical, deliberately limited email-address format."""

    rule_type = "email"
    _email_pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    def validate(self, value: str, context: Mapping[str, Any]) -> str | None:
        del context
        text = _normalise(value)
        if not text:
            return None
        if self._email_pattern.fullmatch(text) is None:
            return "Value must be a valid email address."
        return None


class UniqueRule(ValidationRule):
    """Require a non-empty value to occur once in its column."""

    rule_type = "unique"

    def validate(self, value: str, context: Mapping[str, Any]) -> str | None:
        text = _normalise(value)
        if not text:
            return None
        value_counts = context.get("value_counts")
        if not isinstance(value_counts, Counter):
            raise ConfigurationError("Unique validation requires value counts.")
        if value_counts[text] > 1:
            return "Value must be unique."
        return None


class RuleFactory:
    """Create concrete validation strategies from configuration mappings."""

    _simple_rules: ClassVar[dict[str, type[ValidationRule]]] = {
        "required": RequiredRule,
        "integer": IntegerRule,
        "email": EmailRule,
        "unique": UniqueRule,
    }

    @classmethod
    def create(cls, specification: Mapping[str, Any]) -> ValidationRule:
        """Create one rule or raise ConfigurationError for an invalid spec."""

        if not isinstance(specification, Mapping):
            raise ConfigurationError("Every rule specification must be an object.")

        rule_type = specification.get("type")
        if not isinstance(rule_type, str) or not rule_type.strip():
            raise ConfigurationError("Every rule requires a non-empty 'type'.")
        rule_type = rule_type.strip().lower()

        if rule_type in cls._simple_rules:
            return cls._simple_rules[rule_type]()
        if rule_type == "range":
            return RangeRule(
                minimum=_optional_number(specification, "minimum"),
                maximum=_optional_number(specification, "maximum"),
            )
        raise ConfigurationError(f"Unsupported validation rule: {rule_type!r}.")


class ValidatorEngine:
    """Apply configured rule strategies to tabular rows."""

    def validate(
        self,
        rows: Sequence[Mapping[str, Any]],
        configuration: Mapping[str, Sequence[Mapping[str, Any]]],
        columns: Sequence[str] | None = None,
    ) -> ValidationReport:
        """Validate rows without modifying them and return a report.

        Row numbers match the physical CSV file: the header is row 1 and the
        first data record is row 2.  ``columns`` is optional for general reuse,
        but lets callers validate the schema of an empty CSV file.
        """

        if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
            raise TypeError("Rows must be a sequence of mappings.")
        if not isinstance(configuration, Mapping) or not configuration:
            raise ConfigurationError("The rule configuration must be a non-empty object.")
        if any(not isinstance(row, Mapping) for row in rows):
            raise TypeError("Every row must be a mapping of column names to values.")

        available_columns = set(columns or ())
        for row in rows:
            available_columns.update(str(key) for key in row.keys())
        if not available_columns and not rows:
            available_columns.update(str(key) for key in configuration.keys())

        configured_columns = {str(column) for column in configuration.keys()}
        missing_columns = sorted(configured_columns - available_columns)
        if missing_columns:
            joined = ", ".join(missing_columns)
            raise ConfigurationError(f"Configured column(s) not found: {joined}.")

        rules_by_column: dict[str, tuple[ValidationRule, ...]] = {}
        for raw_column, specifications in configuration.items():
            column = str(raw_column)
            if isinstance(specifications, (str, bytes)) or not isinstance(
                specifications, Sequence
            ):
                raise ConfigurationError(
                    f"Rules for column {column!r} must be a list."
                )
            if not specifications:
                raise ConfigurationError(
                    f"At least one rule is required for column {column!r}."
                )
            rules_by_column[column] = tuple(
                RuleFactory.create(specification) for specification in specifications
            )

        counts_by_column = {
            column: Counter(
                _normalise(row.get(column, ""))
                for row in rows
                if _normalise(row.get(column, ""))
            )
            for column in rules_by_column
        }

        issues: list[ValidationIssue] = []
        for row_number, row in enumerate(rows, start=2):
            for column, rules in rules_by_column.items():
                value = _normalise(row.get(column, ""))
                context = {
                    "row": row_number,
                    "column": column,
                    "value_counts": counts_by_column[column],
                }
                for rule in rules:
                    message = rule.validate(value, context)
                    if message:
                        issues.append(
                            ValidationIssue(
                                row=row_number,
                                column=column,
                                value=value,
                                rule=rule.rule_type,
                                message=message,
                            )
                        )

        return ValidationReport(total_rows=len(rows), issues=tuple(issues))


def _normalise(value: Any) -> str:
    """Convert an input value to the trimmed text used by the rules."""

    if value is None:
        return ""
    return str(value).strip()


def _optional_number(
    specification: Mapping[str, Any], key: str
) -> float | None:
    """Read an optional numeric rule parameter with a clear error message."""

    if key not in specification:
        return None
    value = specification[key]
    if isinstance(value, bool):
        raise ConfigurationError(f"Range {key!r} must be numeric.")
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"Range {key!r} must be numeric.") from error


__all__ = [
    "ConfigurationError",
    "EmailRule",
    "IntegerRule",
    "RangeRule",
    "RequiredRule",
    "RuleFactory",
    "UniqueRule",
    "ValidationIssue",
    "ValidationReport",
    "ValidationRule",
    "ValidatorEngine",
]
