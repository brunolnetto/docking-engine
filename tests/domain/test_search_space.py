import pytest

from moldock.domain import DockingBox, DomainValidationError


def test_box_has_deterministic_identity():
    a = DockingBox(1, 2, 3, 20, 20, 20)
    b = DockingBox(1, 2, 3, 20, 20, 20)

    assert a.search_space_id == b.search_space_id


@pytest.mark.parametrize(
    "sizes",
    [
        (0, 20, 20),
        (-1, 20, 20),
        (20, 0, 20),
        (20, 20, -0.1),
    ],
)
def test_box_rejects_non_positive_dimensions(sizes):
    with pytest.raises(DomainValidationError):
        DockingBox(1, 2, 3, *sizes)
