import pytest

import zeny_project_handler


@pytest.mark.integration
def test_package_exposes_version() -> None:
    assert zeny_project_handler.__version__ == "0.1.0"
