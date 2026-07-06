"""create_app() builds a FastAPI instance without I/O."""

from fastapi import FastAPI

from app.app import create_app


def test_create_app_returns_fastapi_with_title() -> None:
    app = create_app()
    assert isinstance(app, FastAPI)
    assert app.title


def test_factory_and_runner_are_separate_modules() -> None:
    import app.app as factory_module
    import app.main as runner_module

    assert hasattr(factory_module, "create_app")
    assert not hasattr(runner_module, "create_app")
