You have a .asana folder, with numbered entries for your todo list, progress and implementation documentation.

YOU MUST check this, and keep it updated as you work.

```
01-todo.md # Detailed todo list
02-progress.md # Progress report
```

## Project Management
- Use `uv` for Python package management and running tools (NEVER pip)
- Add packages: `uv add package_name`
- Remove packages: `uv remove package_name`
- Running Python tools: `uv run <tool>`
- Run single test: `uv run pytest tests/path_to_test.py::TestClass::test_method -v`
- Type checking: `uv run pyright .`
- Linting: `uv run ruff check .`
- Run formatter: `uv run ruff format .`
- Async testing: use anyio, not asyncio

## Code Style
- Use type hints for function signatures
- Functions must be small and focused
- Error handling: Use try/except with specific exceptions
- Document functions with docstrings (include "why" not just "what")
- Use f-strings for string formatting
- Max line length: 88 characters
- Program in the spirit of A Philosophy of Software Design by John Ousterhout.
- Explicit None checks for Optional types
- YOU MUST add regression tests when your encounter a bug. This should be the first thing you do when you are told about a bug.

### Coding Guidelines

*   **Testing:**
    *   Write code that is easy to test.
    *   Tests are an integral part of the development process.
    *   Start with failing tests and then write code to make them pass (Test-Driven Development principles).
    *   Unit tests should be next to the functionality they test. So in the src/blog/main.py file.
    *   Integration tests should be placed in the tests directory.
    *   AVOID mocks, unless they are requested.
*   **Performance:**
    *   Optimize for readability first.
    *   Performance optimization should only be considered when explicitly required or requested.
*   **Iterative Development:**
    *   Start with the minimum viable solution.
    *   Continuously question if a feature or solution is truly necessary.
    *   Build incrementally based on actual needs, not hypothetical future requirements.
*   **Type Annotations:** Type annotations are **required** in our codebase. This helps with code readability, maintainability, and early error detection.
