---
applyTo: "**/*"
---

# Python Coding Standards & Architecture

## Core Architectural Principles

### SOLID Compliance (Mandatory)
Every class must follow SOLID principles:

1. **Single Responsibility Principle (SRP)**
   - Each class has ONE reason to change.
   - Example: `OrderManager` handles orders, `PositionManager` handles positions.
   - ❌ WRONG: A class that manages orders AND positions AND risk checks.

2. **Open/Closed Principle (OCP)**
   - Open for extension, closed for modification.
   - Use inheritance and composition for new features.
   - Example: Strategy pattern allows new DCA strategies without modifying existing code.

3. **Liskov Substitution Principle (LSP)**
   - Subclasses must be substitutable for their base classes.
   - Example: All `ITradingStrategy` implementations can replace the interface.

4. **Interface Segregation Principle (ISP)**
   - Clients shouldn't depend on interfaces they don't use.
   - Example: Separate `IOrderManager` from `IPositionManager`.

5. **Dependency Inversion Principle (DIP)**
   - Depend on abstractions, not concretions.
   - Example: Strategy depends on `IMarketDataService` interface, not concrete implementation.
   - Use dependency injection throughout.

### Clean Architecture (Mandatory)
Strict separation of concerns across layers:

```
┌─────────────────────────────────────────────┐
│ Presentation Layer (API/Webhooks)          │
│ - src/signals/webhook_handlers.py          │
│ - FastAPI routes, request/response DTOs    │
│ - NO business logic here                   │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Business Logic Layer (Domain)              │
│ - src/strategies/advanced_strategy.py      │
│ - src/position/position_manager.py         │
│ - src/risk/risk_envelope_calculator.py     │
│ - src/domain/decision_context.py           │
│ - Pure domain logic, NO framework deps     │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Data Layer (Persistence/External APIs)     │
│ - src/database/database_manager.py         │
│ - src/trading/alpaca_client.py             │
│ - SQLAlchemy, API clients                  │
└─────────────────────────────────────────────┘
```

**Layer Rules**:
- ✅ Inner layers know NOTHING about outer layers.
- ✅ Dependencies point INWARD only.
- ✅ Domain layer contains NO framework imports.
- ❌ Business logic NEVER imports FastAPI.
- ❌ Data layer NEVER imports domain models directly (use interfaces).

### Async-First (Mandatory)
ALL I/O operations MUST use async/await:

```python
# ✅ CORRECT: Async I/O operations
async def fetch_market_data(self, symbol: str) -> float:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_URL}/{symbol}") as response:
            data = await response.json()
            return data['price']

async def save_position(self, position: Position):
    async with self.db_manager.get_session() as session:
        session.add(position)
        await session.commit()

# ❌ WRONG: Synchronous I/O (blocks event loop)
def fetch_market_data(self, symbol: str) -> float:
    response = requests.get(f"{API_URL}/{symbol}")  # BLOCKS
    return response.json()['price']
```

**Async Rules**:
- Database operations → `async with session`, `await commit()`.
- HTTP requests → `aiohttp`, not `requests`.
- File I/O → `aiofiles`, not built-in `open()`.
- Sleep operations → `asyncio.sleep()`, not `time.sleep()`.
- Concurrent operations → `asyncio.gather()`, not sequential.

### Interface-Based Design (Mandatory)
Always program against interfaces (abstract base classes):

```python
# ✅ CORRECT: Define interfaces first
from abc import ABC, abstractmethod

class IMarketDataService(ABC):
    @abstractmethod
    async def get_current_price(self, symbol: str) -> float:
        """Get current market price for symbol."""
        pass

# Dependency injection with interface
class DCAStrategy:
    def __init__(self, market_data: IMarketDataService):
        self.market_data = market_data  # Interface, not concrete class
```

**Interface Rules**:
- All services MUST have corresponding interfaces in `src/interfaces.py`.
- Use dependency injection, NEVER instantiate services directly.
- Mock interfaces in tests, not concrete implementations.

## Coding Conventions

### Naming
- **Classes**: `PascalCase` (e.g., `OrderManager`).
- **Functions/Variables**: `snake_case` (e.g., `calculate_risk`).
- **Constants**: `UPPER_CASE` (e.g., `MAX_RETRIES`).
- **Booleans**: Should be questions (e.g., `is_active`, `has_permission`).
- **Private Members**: Prefix with `_` (e.g., `_validate_input`).

### Type Hinting
- ALL functions must have complete type annotations.
- Use `typing` module (e.g., `List`, `Dict`, `Optional`, `Union`).
- Use `pydantic` models for data transfer objects (DTOs).

### Error Handling
- Use standardized `DomainError` from `src/domain/errors.py`.
- Include context in exceptions.
- Use `try/except` blocks specifically, avoid bare `except:`.

### Configuration
- ALL magic numbers come from `config/settings.toml` or `src/constants.py`.
- Use `ConfigManager` for runtime access.

### Documentation (Mandatory)
- **Classes**: Must have extensive docstrings explaining purpose, responsibilities, usage examples, and thread-safety notes.
- **Methods**: Must have detailed docstrings explaining purpose, arguments (with types), return values (with types), and exceptions raised.
- **Fields/Properties**: Must have comments or docstrings explaining their purpose and constraints.
- **Complex Logic**: Must have inline comments explaining the "why" behind the logic, not just the "what".
- **Format**: Use Google or Sphinx style docstrings.
