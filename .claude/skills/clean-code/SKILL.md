---
name: clean-code
description: Enforce human-readable Python with the cleancode analyzer. Use this to check existing files or to generate and validate new code based on instructions.
arguments:
  type: object
  properties:
    target_path:
      type: string
      description: The path to the Python file or directory to check.
    instruction:
      type: string
      description: Instruction for generating a new Python file if target_path is not provided.
  required: []
---

# Clean Code Analyzer

Run the `clean-code` static analyzer on the targeted Python file or directory to enforce formatting, structure, and readability standards.

### Workflow

1. **If `target_path` is provided:**
   Execute: `clean-code check "{{target_path}}"`

2. **If no `target_path` is provided but an `instruction` is:**
   * Generate the requested Python code based on the `instruction`.
   * Save the code to a temporary path (`{{generated_file_path}}`).
   * Execute: `clean-code check "{{generated_file_path}}"`

### Guidelines

* By default, `info`-severity violations (the fuzziest, lowest-signal rules) are hidden to avoid context noise. 
* If the summary indicates violations hidden below `--min-severity warning`, and a deeper pass is required, rerun the command with: `clean-code check --min-severity info "{{target_path}}"` (or the generated path).
* Review the output from the analyzer. If any violations are reported, modify the source code directly using the suggested `fix:` patterns. 
* Do not silence violations using inline comments unless specifically requested by the user. 
* Present the final cleaned code back to the user.