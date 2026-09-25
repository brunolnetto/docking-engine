import pytest

from moldock.domain import DomainValidationError, StoredBlob


def make_blob(**overrides):
    values = dict(
        blob_id="blob_1",
        uri="memory://blobs/blob_1",
        sha256="a" * 64,
        size_bytes=1,
    )
    values.update(overrides)
    return StoredBlob(**values)


@pytest.mark.parametrize("field", ["blob_id", "uri", "sha256"])
def test_stored_blob_rejects_blank_required_fields(field):
    with pytest.raises(DomainValidationError):
        make_blob(**{field: " "})


def test_stored_blob_rejects_negative_size():
    with pytest.raises(DomainValidationError):
        make_blob(size_bytes=-1)


def test_stored_blob_accepts_zero_size():
    assert make_blob(size_bytes=0).size_bytes == 0
