"""Module-local test wiring.

Re-exports the shared harness (hermetic env autouse fixture, client factory,
envelope assertion) so module-colocated tests behave exactly like the shared
tree — pytest only walks conftest.py files on the path from rootdir, so the
fixtures must be surfaced here explicitly.
"""

from tests.conftest import *  # noqa: F401,F403 — deliberate fixture re-export
