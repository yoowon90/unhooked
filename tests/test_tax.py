"""Unit tests for ZIP-to-state resolution in the tax helpers."""
import pytest

from website.tax import state_for_zip


@pytest.mark.parametrize("zipcode,expected", [
    ('10001', 'NY'),   # Manhattan
    ('90210', 'CA'),   # Beverly Hills
    ('02108', 'MA'),   # Boston
    ('60601', 'IL'),   # Chicago
    ('77001', 'TX'),   # Houston
])
def test_state_for_zip_resolves_known_zips(zipcode, expected):
    assert state_for_zip(zipcode) == expected


def test_state_for_zip_rejects_non_zip():
    assert state_for_zip('abcde') is None
    assert state_for_zip('1000') is None      # too short
    assert state_for_zip('100010') is None    # too long
    assert state_for_zip('') is None
    assert state_for_zip(None) is None
