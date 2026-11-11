"""Runtime assertions that narrow optional results and mocked test boundaries."""

from unittest.mock import Mock


def require_present[T](value: T | None) -> T:
    """Require a result in a positive test path instead of assuming it exists."""
    assert value is not None, 'Expected the synthetic test result to exist.'
    return value


def require_mock(value: object) -> Mock:
    """Narrow a dependency explicitly replaced by a mock in a test fixture."""
    assert isinstance(value, Mock), 'Expected a mocked test dependency.'
    return value
