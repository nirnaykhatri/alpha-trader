---
applyTo: "**/*"
---

# Documentation Standards & Maintenance

## Documentation Maintenance (MANDATORY)

**CRITICAL**: Every code change MUST update corresponding documentation to keep it live and accurate.

### Update Workflow
When making ANY code changes, you MUST:
1.  **Identify Affected Documentation**: Search for references to modified files in all markdown files (`README.md`, `docs/*.md`, etc.).
2.  **Validate Current Accuracy**: Check if examples still reflect actual code.
3.  **Remove Outdated Content**: Delete deprecated patterns or references.
4.  **Add New Information**: Document new classes, config options, or workflows.
5.  **Update Metadata**: Update line counts, module descriptions, or dependency lists.

### Files Requiring Updates (Priority Order)
1.  `.github/copilot-instructions.md` (and modular instructions)
2.  `README.md`
3.  `ARCHITECTURAL_ENHANCEMENTS_SUMMARY.md`
4.  `docs/*.md` (Specific topic files)

## Markdown Best Practices

### Structure
- **Frontmatter**: Use YAML frontmatter for metadata where appropriate.
- **Headings**: Use ATX-style headings (`#`, `##`, `###`). Hierarchy must be logical.
- **Table of Contents**: Include a TOC for files longer than 100 lines.

### Formatting
- **Code Blocks**: ALWAYS specify the language for syntax highlighting (e.g., \`\`\`python).
- **Lists**: Use hyphens `-` for unordered lists.
- **Emphasis**: Use `**bold**` for emphasis, `*italics*` for minor notes.
- **Links**: Use relative links for internal files (`[Link](./path/to/file.md)`).

### Content
- **Clarity**: Be concise and direct. Use active voice.
- **Examples**: Provide concrete code examples for complex concepts.
- **Admonitions**: Use blockquotes for notes/warnings:
  > **Note**: This is a note.
  > **Warning**: This is a warning.

### Professional Style
- **Consistency**: Maintain consistent terminology throughout the documentation.
- **Spelling/Grammar**: Ensure correct spelling and grammar.
- **Visuals**: Use diagrams (Mermaid or ASCII) to explain architecture or flows.

## Auto-Documentation Pattern
When creating new components, include this workflow:
1.  **Create the code**.
2.  **IMMEDIATELY update instructions**: Add usage patterns to `business_logic.instructions.md` or `python_standards.instructions.md`.
3.  **Update README**: Add to architecture section.
