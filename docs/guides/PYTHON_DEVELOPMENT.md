# Python Development Guide

## 1. Scope and Technology

QSerial uses Python 3, PySide6 with Qt Widgets, pyserial, and PyInstaller. Do not add another GUI framework or a new dependency without explicit user approval and synchronized updates to `requirements.txt`, the bilingual README, and the affected design documents.

## 2. Progressive Workflow

1. Read the [overall design](../design/PROJECT_DESIGN.md) and the linked module design for the intended change.
2. Locate the actual call chain and establish a focused reproduction, characterization test, or other relevant evidence.
3. Make the smallest coherent change that improves correctness or the requested architecture; keep the application runnable.
4. Add or update focused tests before broad refactoring when current behavior is not already protected.
5. Run focused checks, then proportionate regression tests and an actual-diff review.
6. Update current-state design and user documentation in the same change; keep future proposals in `.plan/`.
7. When review finds a problem, fix it and perform an additional focused review of that change before delivery.

Prefer several verified increments over a large, untestable rewrite. Architecture quality comes from clear responsibilities and dependencies, not from the number of classes or layers.

## 3. Python Style

- Save Python source as UTF-8.
- Use `CamelCase` for classes, `snake_case` for functions and variables, and `UPPER_CASE` for constants.
- Group imports as standard library, third-party, and local modules, separated by blank lines.
- Keep one statement per line in new or refactored code; avoid dense semicolon-packed methods.
- Write concise English docstrings or comments for public classes, complex workflows, and non-obvious concurrency decisions.
- Keep public interfaces narrow and mark implementation-only helpers as private.
- Use English for new or updated design and SOP documents; maintain English `README.md` and Chinese `README.zh-CN.md` as separate linked files.
- Use English for script comments, docstrings, diagnostics, and user-facing output.
- Use uppercase filenames for guides, such as `PYTHON_DEVELOPMENT.md` and `VERSION_RELEASE.md`.

## Internationalization

- Use English source strings with `self.tr()` or `QCoreApplication.translate()` and maintain Simplified Chinese Qt translation resources.
- Support `system`, `zh_CN`, and `en_US`; default to `system`, resolving Chinese locales to Simplified Chinese and all others to English.
- Implement `retranslate_ui()` and handle `QEvent.LanguageChange` for existing composite widgets without recreating sessions or translating user data.
- Include both languages in applicable visual review, checking clipping, overflow, readability, and state preservation.

## 4. Ownership and Dependencies

- Parents compose and own child lifetime; children notify upward through explicit callbacks or Qt signals rather than reaching into parent internals.
- Keep Qt widgets and signals out of pure serial, conversion, configuration, and file-writer modules unless Qt adaptation is the module's defined purpose.
- Give each port, worker, file stream, mutable configuration model, and timer a clear owner and cleanup path.
- Reuse existing module boundaries when they are coherent; introduce a module only for a concrete responsibility and update its design in the same change.

## 5. Concurrency and I/O

- Never perform blocking serial reads or continuous log-file writes on the Qt UI thread.
- Preserve bounded receive/log queues and batched editor updates for high-frequency traffic.
- Define the ordering, timeout, late-result, and shutdown behavior of every asynchronous boundary.
- Use events or conditions for deterministic concurrency tests; do not rely on arbitrary sleeps to manufacture a schedule.
- Do not use forced thread termination, unlimited retries, or indefinite UI waits as cleanup mechanisms.

## 6. Errors and External Input

- Catch specific exceptions at the operation or external-input boundary and preserve actionable error context.
- Validate JSON types and values before using them; do not add broad catch-all handlers to hide programming errors.
- Do not invent compatibility conversions for unsupported inputs or speculative future platforms.
- A timeout or write failure must not be presented as successful cleanup or persistence.

## 7. Tests and Delivery

The refactored suite is separated into `tests/unit/`, `tests/component/`, and `tests/e2e/`:

- Unit tests cover pure Python logic, fake serial ports, temporary files, and fault injection without Qt or physical resources.
- Component tests use `PySide6.QtTest.QTest` for mouse/keyboard input and `QSignalSpy` for signal assertions, with offscreen widgets and no physical serial ports.
- E2E scenarios use QTest with the real application widgets and configured virtual/real serial loopback in the [E2E SOP](E2E_TESTING.md); they run separately from the default unit/component suites.

Run the fast suites independently:

```powershell
python3 scripts/generate_translations.py
python3 -m unittest discover -s tests/unit -v
python3 -m unittest discover -s tests/component -v
```

Use `QT_QPA_PLATFORM=offscreen` for component tests where required. Real serial hardware, virtual loopback links, clean-machine execution, and packaged GUI behavior require separate E2E or manual verification when available; never mark an unexecuted scenario as passed.

Every GUI-affecting change requires visual review in addition to functional assertions. Capture the affected widgets or windows with `QWidget.grab()`, inspect the actual PNG images, and check layout, clipping, spacing, contrast, readability, and relevant interaction/theme states. Creating a screenshot without inspecting it is not visual acceptance; if visual review cannot be performed, report it as not run.

Do not commit or release unless explicitly authorized. Authorized commit messages use English Conventional Commits, for example `refactor: isolate receive text rendering`.
