# Road-map

- [x] `fix`: max-depth default should be set to 2
- [x] `fix`: max-parameters default should be set to 3
- [x] `feature`: add a template config file that acts as reference to which rules exist and can be disabled or changed optionally
- [x] `feature`: make the project available as skill for claude code usage
- [x] `feature`: add a rule that enforces meaningful return types & parameter type hints. It should:
      - Reject non-descriptive types like standalone `Any` or redundant `Optional[Any]`.
      - Encourage structured alternatives (e.g., `TypedDict`, `dataclasses`, or `object`).
      - Permit `Any` exclusively in justified exceptions (e.g. an external library returns dict[str|Any] and our function does something to it and returns it)