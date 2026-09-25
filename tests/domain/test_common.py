from moldock.domain.common import content_id


def test_content_id_is_stable_across_mapping_order():
    left = content_id("exp", {"a": 1, "b": 2})
    right = content_id("exp", {"b": 2, "a": 1})

    assert left == right


def test_content_id_changes_when_payload_changes():
    assert content_id("exp", {"x": 1}) != content_id("exp", {"x": 2})
