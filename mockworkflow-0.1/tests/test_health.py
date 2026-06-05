import mockworkflow


def test_package_version_is_available() -> None:
    assert mockworkflow.__version__ == "0.1.0"
