"""DataSure desktop application.

This module contains the Tkinter presentation layer and the small amount of
file input/output needed by the desktop application.  Validation behaviour is
delegated to the independent ``datasure_core`` library.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

from datasure_core import ConfigurationError, ValidationReport, ValidatorEngine


PREVIEW_LIMIT = 100
REPORT_FIELDS = ("row", "column", "value", "rule", "message")


def read_csv_file(path: str | Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read a CSV file and return validated headers and rows.

    UTF-8 with an optional byte-order mark is supported.  Header whitespace is
    removed so that configuration names are predictable.  Missing cell values
    are represented as empty strings; extra cells are treated as malformed.
    """

    with Path(path).open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        raw_headers = reader.fieldnames
        if raw_headers is None:
            raise ValueError("The CSV file must contain a header row.")

        headers = [header.strip() if header else "" for header in raw_headers]
        if not headers or any(not header for header in headers):
            raise ValueError("Every CSV column must have a non-empty header.")
        if len(set(headers)) != len(headers):
            raise ValueError("CSV column headers must be unique.")

        rows: list[dict[str, str]] = []
        for physical_row, raw_row in enumerate(reader, start=2):
            if None in raw_row and raw_row[None]:
                raise ValueError(
                    f"CSV row {physical_row} has more values than the header."
                )
            rows.append(
                {
                    clean_header: raw_row.get(raw_header) or ""
                    for raw_header, clean_header in zip(raw_headers, headers)
                }
            )

    return headers, rows


def read_rule_file(path: str | Path) -> dict[str, list[dict[str, Any]]]:
    """Read a JSON rule configuration and perform basic structural checks."""

    with Path(path).open(encoding="utf-8") as file:
        configuration = json.load(file)
    if not isinstance(configuration, Mapping) or not configuration:
        raise ValueError("The JSON rule configuration must be a non-empty object.")
    return dict(configuration)


def write_validation_report(path: str | Path, report: ValidationReport) -> None:
    """Write a validation report to a UTF-8 CSV file."""

    with Path(path).open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        writer.writerows(issue.as_dict() for issue in report.issues)


class DataSureApp:
    """Single-window graphical interface for the DataSure workflow."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("DataSure - CSV Validator")
        self.root.geometry("1080x700")
        self.root.minsize(850, 560)

        self.rows: list[dict[str, str]] = []
        self.columns: list[str] = []
        self.configuration: dict[str, list[dict[str, Any]]] = {}
        self.report: ValidationReport | None = None
        self.csv_path: Path | None = None
        self.rules_path: Path | None = None
        self.engine = ValidatorEngine()

        self.csv_label = tk.StringVar(value="CSV: not selected")
        self.rules_label = tk.StringVar(value="Rules: not selected")
        self.summary_label = tk.StringVar(value="No validation has been run.")
        self.status_label = tk.StringVar(value="Select a CSV file and a rule file.")

        self._build_interface()
        self._update_button_states()

    def _build_interface(self) -> None:
        container = ttk.Frame(self.root, padding=12)
        container.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(3, weight=1)
        container.rowconfigure(5, weight=1)

        title = ttk.Label(
            container,
            text="DataSure - CSV Validator",
            font=("Segoe UI", 18, "bold"),
        )
        title.grid(row=0, column=0, sticky="w", pady=(0, 10))

        controls = ttk.Frame(container)
        controls.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.open_button = ttk.Button(
            controls, text="Open CSV", command=self.open_csv
        )
        self.open_button.grid(row=0, column=0, padx=(0, 6))
        self.rules_button = ttk.Button(
            controls, text="Load Rules", command=self.load_rules
        )
        self.rules_button.grid(row=0, column=1, padx=6)
        self.validate_button = ttk.Button(
            controls, text="Validate", command=self.validate_data
        )
        self.validate_button.grid(row=0, column=2, padx=6)
        self.export_button = ttk.Button(
            controls, text="Export Report", command=self.export_report
        )
        self.export_button.grid(row=0, column=3, padx=6)

        selected_files = ttk.Frame(container)
        selected_files.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        selected_files.columnconfigure(0, weight=1)
        ttk.Label(selected_files, textvariable=self.csv_label).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(selected_files, textvariable=self.rules_label).grid(
            row=1, column=0, sticky="w"
        )

        preview_frame = ttk.LabelFrame(container, text="Data preview", padding=6)
        preview_frame.grid(row=3, column=0, sticky="nsew")
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)
        self.preview_tree = ttk.Treeview(preview_frame, show="headings")
        preview_vertical = ttk.Scrollbar(
            preview_frame, orient="vertical", command=self.preview_tree.yview
        )
        preview_horizontal = ttk.Scrollbar(
            preview_frame, orient="horizontal", command=self.preview_tree.xview
        )
        self.preview_tree.configure(
            yscrollcommand=preview_vertical.set,
            xscrollcommand=preview_horizontal.set,
        )
        self.preview_tree.grid(row=0, column=0, sticky="nsew")
        preview_vertical.grid(row=0, column=1, sticky="ns")
        preview_horizontal.grid(row=1, column=0, sticky="ew")

        summary = ttk.Label(
            container,
            textvariable=self.summary_label,
            font=("Segoe UI", 10, "bold"),
        )
        summary.grid(row=4, column=0, sticky="w", pady=(10, 5))

        results_frame = ttk.LabelFrame(
            container, text="Validation issues", padding=6
        )
        results_frame.grid(row=5, column=0, sticky="nsew")
        results_frame.rowconfigure(0, weight=1)
        results_frame.columnconfigure(0, weight=1)
        self.results_tree = ttk.Treeview(
            results_frame, columns=REPORT_FIELDS, show="headings"
        )
        result_widths = {
            "row": 60,
            "column": 120,
            "value": 170,
            "rule": 100,
            "message": 360,
        }
        for field in REPORT_FIELDS:
            self.results_tree.heading(field, text=field.replace("_", " ").title())
            self.results_tree.column(
                field,
                width=result_widths[field],
                minwidth=50,
                stretch=field in {"value", "message"},
            )
        results_vertical = ttk.Scrollbar(
            results_frame, orient="vertical", command=self.results_tree.yview
        )
        results_horizontal = ttk.Scrollbar(
            results_frame, orient="horizontal", command=self.results_tree.xview
        )
        self.results_tree.configure(
            yscrollcommand=results_vertical.set,
            xscrollcommand=results_horizontal.set,
        )
        self.results_tree.grid(row=0, column=0, sticky="nsew")
        results_vertical.grid(row=0, column=1, sticky="ns")
        results_horizontal.grid(row=1, column=0, sticky="ew")

        ttk.Label(container, textvariable=self.status_label).grid(
            row=6, column=0, sticky="w", pady=(8, 0)
        )

    def open_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Open CSV file",
            filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            columns, rows = read_csv_file(path)
        except (OSError, UnicodeError, csv.Error, ValueError) as error:
            messagebox.showerror("Cannot open CSV", str(error), parent=self.root)
            self.status_label.set("The CSV file was not loaded.")
            return

        self.csv_path = Path(path)
        self.columns = columns
        self.rows = rows
        self.csv_label.set(f"CSV: {self.csv_path.name}")
        self._show_preview()
        self._clear_report()
        self.status_label.set(
            f"Loaded {len(rows)} data row(s) from {self.csv_path.name}."
        )
        self._update_button_states()

    def load_rules(self) -> None:
        path = filedialog.askopenfilename(
            title="Open validation rules",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            configuration = read_rule_file(path)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            messagebox.showerror("Cannot load rules", str(error), parent=self.root)
            self.status_label.set("The rule configuration was not loaded.")
            return

        self.rules_path = Path(path)
        self.configuration = configuration
        self.rules_label.set(f"Rules: {self.rules_path.name}")
        self._clear_report()
        self.status_label.set(f"Loaded validation rules from {self.rules_path.name}.")
        self._update_button_states()

    def validate_data(self) -> None:
        if self.csv_path is None or self.rules_path is None:
            messagebox.showwarning(
                "Files required",
                "Select a CSV file and load a JSON rule file first.",
                parent=self.root,
            )
            return
        try:
            self.report = self.engine.validate(
                self.rows,
                self.configuration,
                columns=self.columns,
            )
        except (ConfigurationError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Validation configuration error", str(error), parent=self.root
            )
            self.status_label.set("Validation could not be completed.")
            return

        self._show_results()
        self.status_label.set("Validation completed successfully.")
        self._update_button_states()

    def export_report(self) -> None:
        if self.report is None:
            messagebox.showwarning(
                "No report",
                "Run validation before exporting a report.",
                parent=self.root,
            )
            return
        path = filedialog.asksaveasfilename(
            title="Export validation report",
            defaultextension=".csv",
            initialfile="validation_report.csv",
            filetypes=(("CSV files", "*.csv"),),
        )
        if not path:
            return
        try:
            write_validation_report(path, self.report)
        except OSError as error:
            messagebox.showerror("Cannot export report", str(error), parent=self.root)
            self.status_label.set("The report was not exported.")
            return

        messagebox.showinfo(
            "Report exported",
            f"Validation report saved as {Path(path).name}.",
            parent=self.root,
        )
        self.status_label.set(f"Exported validation report to {Path(path).name}.")

    def _show_preview(self) -> None:
        self.preview_tree.delete(*self.preview_tree.get_children())
        self.preview_tree.configure(columns=self.columns)
        for column in self.columns:
            self.preview_tree.heading(column, text=column)
            self.preview_tree.column(column, width=150, minwidth=80, stretch=True)
        for row in self.rows[:PREVIEW_LIMIT]:
            self.preview_tree.insert(
                "", "end", values=tuple(row.get(column, "") for column in self.columns)
            )

    def _show_results(self) -> None:
        self.results_tree.delete(*self.results_tree.get_children())
        if self.report is None:
            return
        for issue in self.report.issues:
            self.results_tree.insert(
                "",
                "end",
                values=(
                    issue.row,
                    issue.column,
                    issue.value,
                    issue.rule,
                    issue.message,
                ),
            )
        self.summary_label.set(
            f"{self.report.total_rows} row(s) | "
            f"{self.report.valid_rows} valid | "
            f"{self.report.invalid_rows} invalid | "
            f"{self.report.issue_count} issue(s)"
        )

    def _clear_report(self) -> None:
        self.report = None
        self.results_tree.delete(*self.results_tree.get_children())
        self.summary_label.set("No validation has been run.")
        self._update_button_states()

    def _update_button_states(self) -> None:
        can_validate = self.csv_path is not None and self.rules_path is not None
        self.validate_button.configure(state="normal" if can_validate else "disabled")
        self.export_button.configure(
            state="normal" if self.report is not None else "disabled"
        )


def main() -> None:
    """Launch the desktop application."""

    root = tk.Tk()
    DataSureApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
