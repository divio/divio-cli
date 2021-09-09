from unittest.mock import MagicMock

from divio_cli import api_requests, messages


def test_upload_db_for_restore_no_db_service(
    base_session, bad_request_response
):
    response_text = "No database available"
    bad_request_response.text = response_text
    db_upload_request = api_requests.UploadDBRequest(base_session)
    db_upload_request.get_login = MagicMock(return_value=False)

    try:
        db_upload_request.verify(bad_request_response)
    except api_requests.APIRequestError as e:
        assert messages.BAD_REQUEST in e.message
        assert response_text in e.message
    else:
        assert False, "No exception raised"
