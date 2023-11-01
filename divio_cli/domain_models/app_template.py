from divio_cli.exceptions import DivioException


class AppTemplate:
    LIST_APP_TEMPLATES_URL_PATH = "/apps/v3/app-templates/"
    GET_APP_TEMPLATE_URL_PATH = "/apps/v3/app-templates/{uuid}"

    class DoesNotExistError(DivioException):
        pass

    @classmethod
    def list(cls, client, page_size=None, page=None):
        app_templates = []
        params = {}

        if page_size is not None:
            params["page_size"] = page_size

        if page is not None:
            params["page"] = page

        app_templates_data = client.get_json(
            path=cls.LIST_APP_TEMPLATES_URL_PATH,
            method="GET",
            params=params,
        )

        for result in app_templates_data["results"]:
            app_templates.append(
                AppTemplate(
                    client=client,
                    uuid=result["uuid"],
                    data=result,
                    refresh=False,
                ),
            )

        return app_templates

    @classmethod
    def retrieve(cls, client, uuid):
        return AppTemplate(client=client, uuid=uuid)

    def __init__(self, client, uuid, data=None, refresh=True):
        self.client = client
        self.uuid = uuid
        self.data = data or {}

        if refresh:
            self.refresh()

    def __repr__(self):
        module_name = self.__class__.__module__
        class_name = self.__class__.__name__

        return f"<{module_name}.{class_name}(client={self.client!r}, uuid={self.uuid!r})>"

    def refresh(self):
        try:
            app_template_data = self.client.get_json(
                path=self.GET_APP_TEMPLATE_URL_PATH.format(uuid=self.uuid),
                method="GET",
            )

            self.data.clear()
            self.data.update(app_template_data)

        except DivioException as original_exception:
            raise self.DoesNotExistError(
                f"No app template with UUID {self.uuid} found",
            ) from original_exception
