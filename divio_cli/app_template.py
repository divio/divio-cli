from divio_cli.exceptions import DivioException


LIST_APP_TEMPLATES_PATH = "/apps/v3/app-templates/"
GET_APP_TEMPLATE_PATH = "/apps/v3/app-templates/{uuid}"


class AppTemplate:
    def __init__(self, client, uuid, data=None):
        self.client = client
        self.uuid = uuid
        self.data = data or {}

    def __repr__(self):
        return (
            f"<divio.AppTemplate(client={self.client!r}, uuid={self.uuid!r})>"
        )

    def pull_data(self):

        try:
            app_template_data = self.client.get_json(
                path=GET_APP_TEMPLATE_PATH.format(uuid=self.uuid),
                method="GET",
            )

            self.data.update(app_template_data)

        except DivioException as original_exception:
            raise self.DoesNotExistError(
                f"No app temlate with UUID {self.uuid} found",
            ) from original_exception

    # class API ###############################################################
    class DoesNotExistError(DivioException):
        pass

    @classmethod
    def filter(cls, client, page_size=None, page=None):
        app_templates = []
        params = {}

        if page_size is not None:
            params["page_size"] = page_size

        if page is not None:
            params["page"] = page

        app_templates_data = client.get_json(
            path=LIST_APP_TEMPLATES_PATH,
            method="GET",
            params=params,
        )

        for result in app_templates_data["results"]:
            app_templates.append(
                AppTemplate(
                    client=client,
                    uuid=result["uuid"],
                    data=result,
                ),
            )

        return app_templates

    @classmethod
    def get(cls, client, uuid):
        try:
            return AppTemplate(
                client=client,
                uuid=uuid,
                data=client.get_json(
                    path=GET_APP_TEMPLATE_PATH.format(uuid=uuid),
                    method="GET",
                ),
            )

        except DivioException as original_exception:
            raise cls.DoesNotExistError(
                f"No app temlate with UUID {uuid} found",
            ) from original_exception
