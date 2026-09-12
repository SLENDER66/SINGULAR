import math

import pytest

from singular.autopilot import ActionRequest


@pytest.mark.parametrize("field", ["impact", "risk", "reversibility"])
def test_action_request_rejects_non_finite_values(field):
    values = {"impact": 1.0, "risk": 1.0, "reversibility": 9.0}
    for value in (math.nan, math.inf, -math.inf):
        values[field] = value
        with pytest.raises(ValueError, match=field):
            ActionRequest("bounded", "bounded action", **values)


def test_action_request_rejects_out_of_range_values():
    with pytest.raises(ValueError, match="between 0 and 10"):
        ActionRequest("bounded", "bounded action", 11, 1, 9)
    with pytest.raises(ValueError, match="between 0 and 10"):
        ActionRequest("bounded", "bounded action", 1, -1, 9)
