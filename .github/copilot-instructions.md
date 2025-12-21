# Trading Bot Copilot Instructions

## Overview
This repository contains a production-grade Python trading bot. These instructions guide Copilot to ensure high-quality, safe, and architecturally sound code generation and review.

## Modular Instructions
Detailed instructions are broken down into modular files in `.github/instructions/`. Copilot should automatically apply these based on the file context.

- **Python Standards**: `.github/instructions/python_standards.instructions.md` (SOLID, Async, Naming)
- **Business Logic**: `.github/instructions/business_logic.instructions.md` (DCA Strategy, Risk, Patterns)
- **Code Review**: `.github/instructions/code_review.instructions.md` (Principal Engineer Persona, Rating)
- **Documentation**: `.github/instructions/documentation.instructions.md` (Maintenance, Markdown Standards)

## Global Guiding Principles

### 1. Safety First
- **Risk Management**: Never bypass risk checks. Always use `RiskEnvelopeCalculator`.
- **Capital Preservation**: Prioritize safety over potential profit.
- **Stop Loss**: Every trade must have a safety mechanism (though this bot uses DCA, safety limits apply).

### 2. Architectural Integrity
- **SOLID Principles**: Strictly adhere to SOLID.
- **Clean Architecture**: Respect layer boundaries. Domain logic never depends on frameworks.
- **Async-First**: No blocking I/O operations.

### 3. Code Quality
- **Principal Engineer Standard**: All code must be rated ≥ 9.5/10.
- **Self-Correction**: If generated code is suboptimal, critique and improve it before presenting.
- **Type Safety**: Full type annotations are mandatory.

### 4. Documentation
- **Live Docs**: Update documentation with every code change.
- **Clarity**: Explain "why", not just "what".

## Quick Reference
- **Main Entry**: `run_bot.py`
- **Config**: `config/settings.toml` (TOML-based configuration)
- **Strategy**: `src/strategies/advanced_strategy.py`
- **Risk**: `src/risk/risk_envelope_calculator.py`

---
*Refer to specific instruction files for detailed patterns and rules.*
