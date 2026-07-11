# Road-map

- [ ] `feature`: add a new rule that counts sequential guard clauses and suggests to the LLM to check if the function can be split into subfunctions that do exactly one thing (as the clean code rule: "do one thing" says)
- [ ] `bug`: when claude code is not available due to contingency expired, an error is displayed to the user instead of handling it by telling that the limit is reached. Add this error handling