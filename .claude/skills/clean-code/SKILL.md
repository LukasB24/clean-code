---
name: clean-code
description: Enforce human-readable Python with the cleancode analyzer. Use this whenever you write or edit Python source (functions, modules, scripts) to catch readability problems like deep nesting, oversized functions, or uninformative Any type hints.
arguments:
  type: object
  properties:
    target_path:
      type: string
      description: The path to the Python file or directory to check.
  required:
    - target_path
---

# Clean Code Analyzer

Run the `clean-code` static analyzer on the targeted Python file or directory to enforce formatting, structure, and readability standards.

! `clean-code check "{{target_path}}"`

Review the output from the analyzer. If any errors or warnings are reported, modify the source code directly using the suggested `fix:` patterns. Do not silence violations using inline comments unless specifically requested by the user. Present the final cleaned code back to the user.