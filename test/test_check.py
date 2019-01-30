from divio_cli.check_system import check_requirements

def test_doctor():
    """
    Run all doctor checks. This is more of an integration test...
    """

    errors = {
        check: error
        for check, check_name, error in check_requirements()
    }
    assert not any(errors.values())