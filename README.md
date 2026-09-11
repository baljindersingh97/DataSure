# DataSure

DataSure is a small desktop CSV validation application created for B144
Software Design and Modeling. It previews a CSV file, loads reusable validation
rules from JSON, displays row-level issues, and exports a CSV report.

The validation behaviour is contained in `datasure_core.py`. The module has no
GUI or file-system dependency and can therefore be imported by other Python
applications.

## Features

- Open and preview a UTF-8 CSV file.
- Load validation rules from JSON.
- Apply required, integer, range, email, and unique rules.
- Display physical CSV row numbers and clear issue messages.
- Summarise valid rows, invalid rows, and issue totals.
- Export issues as a CSV report.
- Handle malformed files and configurations without terminating the GUI.

## Requirements

- Python 3.11 or later.
- Tkinter (included in standard Python distributions on Windows).
- No third-party packages.

Verify Tkinter if necessary:

```powershell
python -m tkinter
```

## Run the application

From the project directory:

```powershell
python app.py
```

Then:

1. Select **Open CSV** and choose `sample_students.csv`.
2. Select **Load Rules** and choose `validation_rules.json`.
3. Select **Validate**.
4. Review the summary and issue table.
5. Select **Export Report** to save the results.

The supplied sample produces four total rows, one valid row, three invalid
rows, and seven rule failures. Duplicate values are reported on every affected
row, which is why both occurrences of student ID `1001` are issues.

## Run the tests

```powershell
python -m unittest -v
```

The repository contains 26 automated tests covering all five rules, the rule
factory, the validation engine, summary calculations, immutability, file
errors, sample integration, and report export.

## Reuse the library without the GUI

```python
import csv
import json

from datasure_core import ValidatorEngine

with open("sample_students.csv", newline="", encoding="utf-8") as file:
    rows = list(csv.DictReader(file))

with open("validation_rules.json", encoding="utf-8") as file:
    rules = json.load(file)

report = ValidatorEngine().validate(rows, rules)

for issue in report.issues:
    print(issue.row, issue.column, issue.message)
```

This example imports no code from `app.py` and creates no Tkinter window.

## Rule configuration

The JSON object's keys are CSV column names. Each value is an ordered list of
rule specifications:

```json
{
  "age": [
    {"type": "required"},
    {"type": "integer"},
    {"type": "range", "minimum": 18, "maximum": 100}
  ]
}
```

| Rule | Parameters | Behaviour |
|---|---|---|
| `required` | None | Rejects an empty or whitespace-only value |
| `integer` | None | Rejects a non-whole-number value |
| `range` | `minimum`, `maximum`, or both | Applies an inclusive numeric range |
| `email` | None | Applies a practical email-format check |
| `unique` | None | Rejects repeated non-empty values in a column |

Empty optional values are ignored by all rules except `required`. A rule that
refers to a missing column or an unknown rule type produces a configuration
error.

## Architecture and design

```text
Tkinter user interface and file operations (app.py)
                         |
                         v
Reusable validation API (datasure_core.py)
                         |
                         v
Rule strategies, result models, and configuration validation
```

The implementation uses:

- **Strategy:** each validation algorithm implements `ValidationRule`.
- **Factory:** `RuleFactory` converts JSON specifications into rule objects.
- **Separation of concerns:** the library has no Tkinter or file-I/O imports.
- **Open/closed principle:** a new rule can extend `ValidationRule` and be
  registered with the factory without changing the engine algorithm.

Full requirements, UML diagrams, architecture decisions, traceability, and
test evidence are in [DESIGN.md](DESIGN.md).

## Project files

```text
app.py                  Desktop interface and file operations
datasure_core.py        Reusable validation library
test_datasure_core.py   Automated tests
sample_students.csv     Synthetic demonstration data
validation_rules.json   Demonstration rules
DESIGN.md               Requirements, design, UML, and test evidence
README.md               Setup, usage, and reuse instructions
```

## Deliberate limitations

- Input and export formats are limited to CSV; rules use JSON.
- Rule configurations are edited as JSON rather than through a visual editor.
- The email rule checks a common format rather than every RFC email case.
- The complete CSV is held in memory.
- Validation runs on the GUI thread, so very large files may temporarily pause
  the interface.
- The application reports errors but does not alter or repair source data.

These constraints keep the application focused on the assessed problem rather
than adding unrelated features.

## Submission links

- GitHub repository: **ADD ACCESSIBLE REPOSITORY URL BEFORE SUBMISSION**
- Demonstration video: **ADD ACCESSIBLE VIDEO URL BEFORE SUBMISSION**

## Author

- Name: **ADD FULL NAME**
- Student ID: **ADD STUDENT ID**
- Module: B144 Software Design and Modeling
