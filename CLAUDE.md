# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync -U --extra test   # Install dependencies (including test extras)
uv run app.py             # Run the application
uv run pytest             # Run tests
uv run ruff check --fix <file_path>   # Lint a file
uv run ruff format <file_path>        # Format a file
```

Run both ruff commands on every file with business logic changes before finishing.

## Architecture

**Tech stack**: Python 3.14, PySide6, PySide6-Fluent-Widgets (qfluentwidgets)

```
app.py              # Entry point
base/               # Core base classes, event bus, logging
  Base.py           # Event enums, state enums, base class methods
  EventManager.py   # Event bus implementation
  LogManager.py     # Logging manager
frontend/           # UI pages (PySide6)
  AppFluentWindow.py
  Translation/      # Translation-related pages
  Setting/          # Settings pages
module/             # Business modules
  Config.py         # App config singleton
  Data/             # DataManager, ProjectSession, LGDatabase (.lg SQLite)
  Engine/           # Translation engines
  File/             # FileManager (unified file read/write)
  Localizer/        # Localization strings (ZH + EN, line-count must stay equal)
tests/              # Automated tests
widget/             # Custom UI widgets
resource/preset/    # Built-in prompt presets, glossaries
```

### Key systems

**Event bus** — components communicate via `Base.emit` / `Base.subscribe`, never directly:
```python
self.emit(Base.Event.TRANSLATION_DONE, {"result": "success"})
self.subscribe(Base.Event.PROJECT_LOADED, self.on_project_loaded)
```

**Data layer** — `DataManager` is the single entry point; batch writes go through `DataManager.update_batch()`. `ProjectSession` is the single source of truth for session state. Never share mutable object references across modules.

**Config** — `Config.get()` is the single source for app configuration.

**Logging** — always `LogManager.get().debug/info/warning/error(msg, e)`. Pass the exception `e` to capture stack traces automatically; never call `traceback.format_exc()` manually.

**Localization** — all user-visible strings (toasts, dialogs, UI copy) must be defined in `module/Localizer/`. Access via `Localizer.get().your_variable_name`. Ruff excludes the Localizer directory.

## Code Conventions

- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants. **No leading underscores** (`_method`, `_var` are forbidden).
- **Type hints**: mandatory on all function parameters and return values; use `A | None` and `list[str]` over `Optional`/`List`.
- **Data carriers**: prefer `@dataclass`; use `@dataclass(frozen=True)` for cross-thread payloads.
- **No magic values**: use constants or `StrEnum` instead of bare strings/numbers.
- **Control flow**: explicit `if/elif/else`; flatten nested branches with `elif`.
- **UI**: use `qfluentwidgets` components; support light/dark themes (no hardcoded colors); run heavy work in `threading.Thread`; update UI only from the event bus, never from background threads.
- **Module exports**: modules expose only classes; constants/enums are class attributes.
- **Standard library first**: reach for third-party libs only when stdlib cannot meet the need.
- **Comments**: every class, method, and non-obvious logic block must have a `# …` comment explaining *why*.
