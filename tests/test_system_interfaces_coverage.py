from types import SimpleNamespace

import pytest

from src.shared.system_interfaces import SystemAccess, system_access


@pytest.mark.parametrize(
    ("access", "error"),
    [
        (None, RuntimeError),
        (object(), TypeError),
        (SystemAccess(handles=frozenset({str})), TypeError),
    ],
)
def test_system_access_rejects_invalid_declarations(access, error):
    with pytest.raises(error):
        system_access(SimpleNamespace(id="invalid-system", access=access))
