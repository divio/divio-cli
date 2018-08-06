import os

import click
import requests
from six.moves.urllib_parse import urljoin

from . import messages
from .utils import create_temp_dir, get_user_agent


class SingleHostSession(requests.Session):
    def __init__(self, host, **kwargs):
        super(SingleHostSession, self).__init__()
        self.debug = kwargs.pop("debug", False)
        self.host = host.rstrip("/")

        default_proxies = {}

        try:
            default_proxies["http"] = os.environ["HTTP_PROXY"]
        except KeyError:
            pass

        try:
            default_proxies["https"] = os.environ["HTTPS_PROXY"]
        except KeyError:
            pass

        if default_proxies:
            default_proxies.update(kwargs.get("proxies", {}))
            kwargs["proxies"] = default_proxies

        for key, value in kwargs.items():
            setattr(self, key, value)

    def request(self, method, url, *args, **kwargs):
        url = urljoin(self.host, url)
        return super(SingleHostSession, self).request(
            method, url, *args, **kwargs
        )


class APIRequest(object):
    network_exception_message = messages.NETWORK_ERROR_MESSAGE
    default_error_message = messages.SERVER_ERROR
    response_code_error_map = {
        requests.codes.forbidden: messages.AUTH_INVALID_TOKEN,
        requests.codes.not_found: messages.RESOURCE_NOT_FOUND,
    }

    method = "GET"
    url = None
    default_headers = {"User-Agent": get_user_agent()}
    headers = {}

    def __init__(
        self,
        session,
        url=None,
        url_kwargs=None,
        data=None,
        files=None,
        *args,
        **kwargs,
    ):
        self.session = session
        if url:
            self.url = url
        self.url_kwargs = url_kwargs or {}
        self.data = data or {}
        self.files = files or {}

    def __call__(self, *args, **kwargs):
        return self.request(*args, **kwargs)

    def get_url(self):
        return self.url.format(**self.url_kwargs)

    def get_error_code_map(self):
        return self.response_code_error_map

    def get_headers(self):
        headers = self.default_headers.copy()
        headers.update(self.headers)
        return headers

    def request(self, *args, **kwargs):
        try:
            response = self.session.request(
                self.method,
                self.get_url(),
                data=self.data,
                files=self.files,
                headers=self.get_headers(),
                *args,
                **kwargs,
            )
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as e:
            raise click.ClickException(messages.NETWORK_ERROR_MESSAGE + str(e))

        return self.verify(response)

    def verify(self, response):
        if not response.ok:
            error_msg = self.get_error_code_map().get(response.status_code)
            if not error_msg:
                response_content = response.content
                if not self.session.debug:
                    response_content = response_content[:300]
                error_msg = "{}\n\n{}".format(
                    self.default_error_message, response_content
                )
            raise click.ClickException(error_msg)
        return self.process(response)

    def process(self, response):
        return response.json()


class RawResponse(object):
    def process(self, response):
        return response


class TextResponse(object):
    def process(self, response):
        return response.text


class JsonResponse(object):
    def process(self, response):
        return response.json()


class DjangoFormMixin(object):
    success_message = "Request successful"

    def verify(self, response):
        if response.ok:
            return self.success_message
        elif response.status_code == requests.codes.bad_request:
            formatted = (
                "There was an error submitting your request:\n"
                "-------------------------------------------\n\n"
            )
            for field, errors in response.json().items():
                formatted += " - {}\n".format(field)
                for error in errors:
                    formatted += "   - {}\n".format(error)
                formatted += "\n"
            return formatted.strip("\n")
        return super(DjangoFormMixin, self).verify(response)


class FileResponse(object):
    def __init__(self, *args, **kwargs):
        self.filename = kwargs.pop("filename", None)
        self.directory = kwargs.pop("directory", None)
        super(FileResponse, self).__init__(*args, **kwargs)

    def process(self, response):
        dump_path = os.path.join(
            self.directory or create_temp_dir(), self.filename or "data.tar.gz"
        )

        with open(dump_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
                    f.flush()
        return dump_path

    def request(self, *args, **kwargs):
        kwargs["stream"] = True
        return super(FileResponse, self).request(*args, **kwargs)


class LoginRequest(APIRequest):
    default_error_message = messages.AUTH_SERVER_ERROR
    url = "/api/v1/login-with-token/"
    method = "POST"


class LoginStatusRequest(APIRequest):
    url = "/track/"
    method = "GET"


class ProjectListRequest(APIRequest):
    url = "/api/v1/user-websites/"


class ProjectDetailRequest(APIRequest):
    url = "/api/v1/website/{website_id}/detail/"


class DeployProjectProgressRequest(JsonResponse, APIRequest):
    url = "/api/v1/website/{website_id}/deploy/"
    method = "GET"


class DeployLogRequest(JsonResponse, APIRequest):
    url = "api/v1/website/{website_id}/deploy-log/{stage}/"
    method = "GET"


class DeployProjectRequest(JsonResponse, APIRequest):
    url = "/api/v1/website/{website_id}/deploy/"
    method = "POST"


class RegisterAddonRequest(DjangoFormMixin, JsonResponse, APIRequest):
    url = "/api/v1/addon/register/"
    method = "POST"
    success_message = "Addon successfully registered"


class UploadAddonRequest(TextResponse, APIRequest):
    url = "/api/v1/apps/"
    method = "POST"


class UploadBoilerplateRequest(TextResponse, APIRequest):
    url = "/api/v1/boilerplates/"
    method = "POST"


class ProjectLockQueryRequest(APIRequest):
    url = "/api/v1/website/{website_id}/lock/"
    method = "GET"

    def process(self, response):
        return response.json("is_locked")


class ProjectLockRequest(TextResponse, APIRequest):
    url = "/api/v1/website/{website_id}/lock/"
    method = "PUT"


class ProjectUnlockRequest(TextResponse, APIRequest):
    url = "/api/v1/website/{website_id}/lock/"
    method = "DELETE"


class SlugToIDRequest(APIRequest):
    url = "/api/v1/slug-to-id/{website_slug}/"

    def process(self, response):
        return response.json().get("id")


class IDToSlugRequest(APIRequest):
    url = "/api/v1/id-to-slug/{website_id}/"

    def process(self, response):
        return response.json().get("slug")


class DownloadBackupRequest(FileResponse, APIRequest):
    url = "/api/v1/workspace/{website_slug}/download/backup/"
    headers = {"accept": "application/x-tar-gz"}

    def verify(self, response):
        if response.status_code == requests.codes.not_found:
            # no backups yet, ignore
            return None
        return super(DownloadBackupRequest, self).verify(response)


# Download DB


class DownloadDBRequestRequest(JsonResponse, APIRequest):
    url = "/api/v1/website/{website_id}/download/db/request/"
    method = "POST"


class DownloadDBProgressRequest(JsonResponse, APIRequest):
    method = "GET"


# Download Media


class DownloadMediaRequestRequest(JsonResponse, APIRequest):
    url = "/api/v1/website/{website_id}/download/media/request/"
    method = "POST"


class DownloadMediaProgressRequest(JsonResponse, APIRequest):
    method = "GET"


# Upload DB


class UploadDBRequest(JsonResponse, APIRequest):
    url = "/api/v1/website/{website_id}/upload/db/"
    method = "POST"

    def get_error_code_map(self):
        error_codes = super(UploadDBRequest, self).get_error_code_map()
        error_codes[requests.codes.bad_request] = messages.INVALID_DB_SUBMITTED
        return error_codes

    def verify(self, response):
        if response.status_code == requests.codes.bad_request:
            try:
                db_log = response.json()["message"].encode("utf-8")
            except (TypeError, IndexError):
                pass
            else:
                logfile = os.path.join(os.getcwd(), "db_upload.log")
                with open(logfile, "w+") as fh:
                    fh.write(db_log)

        return super(UploadDBRequest, self).verify(response)


class UploadDBProgressRequest(JsonResponse, APIRequest):
    method = "GET"


# Upload Media


class UploadMediaFilesRequest(JsonResponse, APIRequest):
    url = "/api/v1/website/{website_id}/upload/media/"
    method = "POST"


class UploadMediaFilesProgressRequest(JsonResponse, APIRequest):
    method = "GET"


class GetEnvironmentVariablesRequest(JsonResponse, APIRequest):
    url = "/api/v1/website/{website_id}/env/{stage}/environment-variables/"


class GetCustomEnvironmentVariablesRequest(JsonResponse, APIRequest):
    url = "/api/v1/website/{website_id}/env/{stage}/environment-variables/custom/"


class SetCustomEnvironmentVariablesRequest(JsonResponse, APIRequest):
    method = "POST"
    url = "/api/v1/website/{website_id}/env/{stage}/environment-variables/custom/"
