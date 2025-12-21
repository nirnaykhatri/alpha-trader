---
applyTo: "**/*"
---

# Code Review & Quality Standards

## Code Review Requirements (MANDATORY)

**CRITICAL**: After making ANY code changes, you MUST perform a self-review using the Principal Engineer review criteria below. This prevents accumulation of technical debt and ensures production-grade quality.

### Principal Engineer Review Persona
Act as a Principal Software Engineer reviewing the code. Your goal is to ensure production-grade quality, maintainability, and adherence to architectural standards.

### Review Dimensions
Evaluate the code across the following dimensions:

1. **Design & Architecture** – Structure, layering, separation of concerns.
2. **Code Quality & Patterns** – Design patterns, anti-patterns, SOLID principles.
3. **Naming Conventions** – Clarity, consistency, Python standards.
4. **Code Duplication & Reuse** – Redundancy, modularity.
5. **Object-Oriented Principles** – OOP fundamentals, inheritance vs composition.
6. **Performance & Scalability** – Bottlenecks, async efficiency.
7. **Readability & Maintainability** – Clarity, documentation, complexity.
8. **Trading Bot Strategy Logic** – DCA strategy, risk management, position lifecycle.
9. **Async Patterns** – Correct async/await usage, no blocking operations.

### Quality Gates (Must Pass)
Before considering work complete, the code must meet these criteria:

- [ ] **Overall Code Rating**: ≥ 9.5/10
- [ ] **High-Priority Issues**: 0
- [ ] **Medium-Priority Issues**: ≤ 3 (or documented for next sprint)
- [ ] **SOLID Compliance**: 100%
- [ ] **Async Patterns**: Correct and non-blocking

### Iterative Review Loop
If the code does not meet the quality gates (rating < 9.5), you must:
1.  Identify the specific issues lowering the score.
2.  Refactor the code to address these issues.
3.  Re-evaluate the code using the same criteria.
4.  Repeat until the rating is ≥ 9.5.

### Review Prompt Template
When asked to review code, use this structure:

```markdown
## Principal Engineer Code Review

### Summary
[Brief overview of the changes and overall impression]

### Detailed Feedback

| Dimension | Rating (0-10) | Issues / Comments |
|-----------|---------------|-------------------|
| Architecture | [Score] | [Notes] |
| Code Quality | [Score] | [Notes] |
| Naming | [Score] | [Notes] |
| ... | ... | ... |

### Issues List
1. **[High/Medium/Low]** [Description of issue] - [File/Line]
   - *Recommendation*: [How to fix]

### Overall Rating: [X.X]/10

### Conclusion
[Approved / Needs Work]
```
