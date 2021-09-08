from unittest.mock import MagicMock

import pytest

from divio_cli import api_requests


def test_upload_db_for_restore_no_db_service(
    base_session, bad_request_response
):
    response_text = "No database available"
    bad_request_response.text = response_text
    db_upload_request = api_requests.UploadDBRequest(base_session)
    db_upload_request.get_login = MagicMock(return_value=False)
    with pytest.raises(api_requests.APIRequestError):
        assert response_text in db_upload_request.verify(bad_request_response)
