import os
from urllib.parse import urljoin, urlparse

import requests

from divio_cli.exceptions import DivioException

from . import messages
from .utils import create_temp_dir, get_user_agent


class SingleHostSession(requests.Session):
    def __init__(self, host, **kwargs):
        super().__init__()
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

    def request(self, method, url, v3_compatibilty=False, *args, **kwargs):
        url = urljoin(self.host, url)
        if v3_compatibilty:
            # V3 compatibility hack
            url = url.replace("control", "api", 1)
            # All v3 endpoints support JSON, and some use nested data structures
            # that do not work with url-encoded body
            kwargs["json"] = kwargs.pop("data", {})
        return super().request(method, url, *args, **kwargs)


class APIRequestError(DivioException):
    pass


class NetworkError(DivioException):
    pass


class APIRequest:
    network_exception_message = messages.NETWORK_ERROR_MESSAGE
    default_error_message = messages.SERVER_ERROR
    response_code_error_map = {
        requests.codes.forbidden: messages.AUTH_INVALID_TOKEN,
        requests.codes.unauthorized: messages.AUTH_INVALID_TOKEN,
        requests.codes.not_found: messages.RESOURCE_NOT_FOUND_ANONYMOUS,
        requests.codes.bad_request: messages.BAD_REQUEST,
    }

    method = "GET"
    url = None
    default_headers = {"User-Agent": get_user_agent()}

    def __init__(
        self,
        session,
        url=None,
        url_kwargs=None,
        params=None,
        data=None,
        files=None,
        headers=None,
        *args,
        **kwargs,
    ):

        self.session = session
        if url:
            self.url = url
        self.url_kwargs = url_kwargs or {}
        self.params = params or {}
        self.data = data or {}
        self.files = files or {}

        self.headers = {
            **self.default_headers,
            **(headers or {}),
        }

    def __call__(self, *args, **kwargs):

        return self.request(*args, **kwargs)

    def get_url(self):
        return self.url.format(**self.url_kwargs)

    def get_login(self):
        """Tries to get the login name for the current request"""
        # import done here to prevent circular import
        from . import cloud

        netrc = cloud.WritableNetRC()
        host = urlparse(self.session.host).hostname
        data = netrc.hosts.get(host)
        if data:
            return data[0]
        return False

    def get_error_code_map(self, login=None):
        # if a login is provided, change the errormessages accordingly
        if login:
            self.response_code_error_map[
                requests.codes.not_found
            ] = messages.RESOURCE_NOT_FOUND.format(login=login)

        return self.response_code_error_map

    def request(self, *args, **kwargs):
        try:
            response = self.session.request(
                self.method,
                self.get_url(),
                *args,
                data=self.data,
                files=self.files,
                headers=self.headers,
                params=self.params,
                **kwargs,
            )
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as e:
            raise NetworkError(messages.NETWORK_ERROR_MESSAGE + str(e))

        return self.verify(response)

    def verify(self, response):
        if not response.ok:
            error_msg = self.get_error_code_map(self.get_login()).get(
                response.status_code, self.default_error_message
            )
            response_content = response.text
            if not self.session.debug:
                response_content = response_content[:300]
            if response_content:
                # Try to extract all errors separately and build a prettified error message.
                # non_field_errors is the default key our APIs are using for returning such errors.
                try:
                    non_field_errors = "\n".join(
                        list(response.json()["non_field_errors"])
                    )
                    error_msg = f"{error_msg}\n\n{non_field_errors}"
                # Must keep this generic due to compatibility issues of requests library for json decode exceptions.
                except Exception:
                    error_msg = f"{error_msg}\n\n{response_content}"
            raise APIRequestError(error_msg)
        return self.process(response)

    def process(self, response):
        return response.json()


class APIV3Request(APIRequest):
    def request(self, *args, **kwargs):
        return super().request(*args, v3_compatibilty=True, **kwargs)


class RawResponse:
    def process(self, response):
        return response


class TextResponse:
    def process(self, response):
        return response.text


class JsonResponse:
    def process(self, response):
        return response.json()


class DjangoFormMixin:
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
                formatted += f" - {field}\n"
                for error in errors:
                    formatted += f"   - {error}\n"
                formatted += "\n"
            return formatted.strip("\n")
        return super().verify(response)


class FileResponse:
    def __init__(self, *args, **kwargs):
        self.filename = kwargs.pop("filename", None)
        self.directory = kwargs.pop("directory", None)
        super().__init__(*args, **kwargs)

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
        return super().request(*args, **kwargs)


class ProjectListRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/applications/"


class ProjectDetailRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/applications/{application_uuid}/"


class OrganisationDetailRequest(JsonResponse, APIV3Request):
    url = "/iam/v3/organisations/{organisation_uuid}/"


class GetCurrentUserRequest(JsonResponse, APIV3Request):
    url = "/iam/v3/me/"


class DeploymentByApplicationRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/deployments/?application={application_uuid}&environment={environment_uuid}"

    def process(self, response):
        return response.json()["results"][0]


class DeployProjectRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/deployments/"
    method = "POST"


class RegisterAddonRequest(DjangoFormMixin, JsonResponse, APIV3Request):
    url = "/legacy/v3/addons/"
    method = "POST"
    success_message = "Addon successfully registered"


class UploadAddonRequest(TextResponse, APIRequest):
    url = "/api/v1/apps/"
    method = "POST"


class UploadBoilerplateRequest(TextResponse, APIRequest):
    url = "/api/v1/boilerplates/"
    method = "POST"


class SlugToAppUUIDRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/applications/?slug={website_slug}"


class CreateBackupRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/backups/"
    method = "POST"


class GetBackupRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/backups/{backup_uuid}/"
    method = "GET"


class GetServiceInstanceBackupRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/service-instance-backups/{backup_si_uuid}/"
    method = "GET"


class CreateBackupDownloadRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/backup-downloads/"
    method = "POST"


class ListBackupDownloadServiceInstancesRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/backup-download-service-instances/"
    method = "GET"


class GetBackupDownloadServiceInstanceRequest(JsonResponse, APIV3Request):
    url = (
        "/apps/v3/backup-download-service-instances/{backup_download_si_uuid}"
    )


# Create backup and restore using upload (pull)


class CreateBackupUploadRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/backups/upload/"
    method = "POST"


class FinishBackupUploadRequest(JsonResponse, APIV3Request):
    # URL => found in the CreateBackupUploadRequest response body
    method = "POST"

    def __init__(self, session, *args, **kwargs):
        # Do not use session, just a simple requests.request() call.
        super().__init__(requests, *args, **kwargs)


class CreateBackupRestoreRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/backup-restores/"
    method = "POST"


class GetBackupRestoreRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/backup-restores/{backup_restore_uuid}/"
    method = "GET"


# Environment variables


class GetEnvironmentVariablesRequest(JsonResponse, APIV3Request):
    method = "GET"
    url = "/apps/v3/environment-variables/"


# Repository


class RepositoryRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/repositories/{repository_uuid}/"
    method = "GET"


class LogRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/environments/{environment_uuid}/logs/"
    method = "GET"


class EnvironmentListRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/environments/?application={application_uuid}&slug={slug}"
    method = "GET"


class EnvironmentRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/environments/{environment_uuid}/"
    method = "GET"


class DeployLogRequest(JsonResponse, APIV3Request):
    url = "apps/v3/deployments/{deployment_uuid}/logs"
    method = "GET"


class DeploymentsRequest(JsonResponse, APIV3Request):
    url = "apps/v3/deployments/"
    method = "GET"


class DeploymentRequest(JsonResponse, APIV3Request):
    url = "apps/v3/deployments/{deployment_uuid}/"
    method = "GET"


class DeploymentEnvironmentVariablesRequest(JsonResponse, APIV3Request):
    url = "apps/v3/deployments/{deployment_uuid}/environment-variables"
    method = "GET"


class ApplicationRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/applications/{application_uuid}/"
    method = "GET"


class ListServiceInstancesRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/service-instances/?environment={environment_uuid}"
    method = "GET"


class CreateServiceInstanceRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/service-instances/"
    method = "POST"


class ListServicesRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/services/?{filter_region}&{filter_website}"
    method = "GET"


class ListRegionsRequest(JsonResponse, APIV3Request):
    url = "/apps/v3/regions/"
    method = "GET"


class ListOrganisationsRequest(JsonResponse, APIV3Request):
    url = "/iam/v3/organisations/"
    method = "GET"


# Legacy


class LegacyListApplicationsRequest(JsonResponse, APIV3Request):
    url = "/legacy/v3/applications/?id={id}"
    method = "GET"
