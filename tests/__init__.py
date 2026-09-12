"""Test package.

`tests` must remain an importable package: several test modules share fixtures
via `from tests.test_x import ...`. Without this file the same test module is
executed twice under two different module names (`test_x` and `tests.test_x`),
which duplicates module-level side effects such as execution-capability
registration and interrupts collection.
"""
