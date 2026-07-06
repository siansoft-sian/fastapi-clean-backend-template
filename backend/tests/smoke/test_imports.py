"""Every module under app.* imports cleanly and without side effects.

`app.modules.*` is excluded: it stays empty in M0 and future modules are
covered by their own tests.
"""

import importlib
import pkgutil

import app


def test_all_app_modules_import() -> None:
    failures: list[tuple[str, str]] = []
    for module_info in pkgutil.walk_packages(app.__path__, prefix="app."):
        name = module_info.name
        if ".modules." in name:
            continue
        try:
            importlib.import_module(name)
        except Exception as exc:  # collecting every failure for one readable report
            failures.append((name, repr(exc)))
    assert not failures, f"modules failed to import: {failures}"
