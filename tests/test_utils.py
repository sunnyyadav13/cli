import pytest

from httpie.utils import humanize_bytes


def test_humanize_bytes_is_deprecated():
    with pytest.deprecated_call():
        assert humanize_bytes(1024, precision=1) == '1.0 kB'
