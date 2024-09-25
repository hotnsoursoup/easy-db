from typing import Any, Literal
from warnings import warn
from pydantic import (
    BaseModel,
    Field,
    RootModel,
    ValidationError,
    model_validator,
)

from models.exceptions import ModelValidationErrors
from utils.utils import flatten_str


# Error and warning messages
messages = {
    "missing_connection": """
        Connection parameter information is missing. Provide a uri
        or complete connection parameters.""",
    "invalid_connector": "Invalid connector specified.",
    "missing_connector_with_connection_string": """
        Connector must be specified with a connection string.""",
    "missing_dialect": "Dialect is missing and no connection string provided.",
    "uri_or_params": """ 
        Either `uri` or `connection_params` must be provided for 
        non-sqlite dialects.""",
    "uri_and_params": "Both `uri` and `params` are provided. Uri will be used",
    "sqlite_path": "`path` is required when `dialect` is `sqlite`.",
    "missing_driver": "Driver is required when using ODBC connections.",
    "invalid_model": "Invalid model. Choices are `single`, `multi`, and `all`.",
    "paging_error": "Paging is enabled but page_size is missing or set to 0",
}

messages = {key: flatten_str(msg) for key, msg in messages.items()}

# Field descriptions
d = {
    "database_default": """
        Used when identifying the default database loaded 
        used by all connections without an explicitly defined DB
        """,
    "database_uri": """
        For SQL Alchemy, this can be the connection string
        or without arguments. For ODBC, this is the DSN name.
        """,
    "database_params": """
        Connection string params such as host, username, password, etc 
        are stored here.for the database. 
        """,
    "sqlite_path": "The path to the SQLite database file.",
    "database_driver": """
        The driver to use with the connection. Driver definition may 
        vary between dialects and if odbc support is enabled.
        """,
    "options": """
        A dictionary of options to send to create_engine(). 
        """,
    "fetch_return": """Set the default behavior when using execute(query, fetch=fetch).
        - default: Returns a tuple (data, result_object).
        - object: Returns the result object.
        - data: Returns the data as a list of dictionaries.""",
    "use_odbc": "Enable the ODBC support.",
    "auto_commit": "Automatically commit to database.",
    "description": "A description of the database connection.",
    "output": "The output format for the database connection.",
    "paging": """Enable paging for all raw sql queries. Requires page_size. 
        If enabled, the model will add paging to all raw queries passed in.""",
    "paging_config": "Pagination configuration for raw sql queries.",
    "page_size": "Results returned in one query",
    "min_page_size": "Minimum threshold of results before paging begins.",
}

# Flattens the message for any print statements
d = {key: flatten_str(msg) for key, msg in d.items()}


class ConnectionParams(BaseModel):
    driver: str | None = Field(description=d["database_driver"])
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    options: dict[str, str] | None = Field(None, description=d["options"])


class Paging(BaseModel):
    enabled: bool | None = Field(False, description=d["paging"])
    page_size: int | None = Field(None, description=d["page_size"])
    min_page_size: int | None = Field(0, description=d["min_page_size"])


class DatabaseModel(BaseModel):  # isort:skip
    """Pydantic model to validate the database configuration has the
    necessary information to connect to a database.
    """

    description: str | None = Field(None, description=d["description"])
    default: bool | None = Field(False, description=d["database_default"])
    dialect: Literal["mysql", "mariadb", "mssql", "postgresql", "oracle", "sqlite"]
    use_odbc: bool | None = Field(False, description=d["use_odbc"])
    uri: str | None = Field(None, description=d["database_uri"])
    connection_params: ConnectionParams | None = Field(
        None, description=d["database_params"]
    )
    auto_commit: bool | None = Field(False, description=d["auto_commit"])
    path: str | None = Field(None, description=d["sqlite_path"])
    paging: Paging | None = Field(None, description=d["paging_config"])
    fetch_return: Literal["data", "tuple", "object"] = Field(
        "data", description=d["fetch_return"]
    )

    @model_validator(mode="before")
    def field_validation(cls, values: dict) -> dict:
        errors = []
        dialect = values.get("dialect")
        uri = values.get("uri")
        params = values.get("connection_params", {})
        use_odbc = values.get("use_odbc")
        driver = values.get("driver")
        paging = values.get("paging")

        if paging is not None and paging.get("enabled"):
            page_size = paging.get("page_size")
            if page_size is None or page_size == 0:
                errors.append(ValueError(messages["paging_error"]))

        if not driver:
            driver = params.get("driver") if params else None

        if dialect == "sqlite":
            if not values.get("path"):
                errors.append(ValueError(messages["sqlite_path"]))
        else:
            if not (uri or params):
                errors.append(ValueError(messages["uri_or_params"]))
            if not uri:
                if not params.get("user") and not params.get("host"):
                    errors.append(ValueError(messages["missing_connection"]))
            if uri and params:
                warn(messages["uri_and_params"])
        if use_odbc and not driver:
            errors.append(ValueError(messages["missing_driver"]))
        if len(errors) > 0:
            error_msg = "\n  - ".join([str(e) for e in errors])
            raise ValueError(error_msg)
        return values


class MultiDatabaseModel(RootModel[dict[str, DatabaseModel]]):
    """
    Model for multidatabase configurations. Conifigurations that
    are defined with a root key (database name) and only have 1 value
    will pass validation.

    e.g.

    mydatabase1:
      dialect: mysql
      uri: mysql://user:pass
    """

    @model_validator(mode="before")
    def ensure_values_are_dict(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            raise ValueError("Root must be a dictionary.")
        for key, value in values.items():
            if not isinstance(value, dict):
                raise ValueError(f"Value for '{key}' must be a dictionary.")
        return values


models = {"single": DatabaseModel, "multi": MultiDatabaseModel}


def validate_db_model(db_config: dict[str, Any]) -> BaseModel | ValidationError:
    """
    Validate the database configuration dictionary with all available
    models. Returns the validated model or a ValidationError containing
    all encountered errors if all models fail.
    """
    db_config = db_config["db"] if "db" in db_config else db_config
    model_errors = {}

    for model_class in models.values():
        try:
            model_instance = model_class(**db_config)
            return model_instance
        except ValidationError as e:
            model = model_class.__name__
            model_errors[model] = e.errors()

    raise ModelValidationErrors(model_errors)


def get_nested_config(config: dict) -> dict:
    """
    Retrieves nested database configurations
    """
    if "db" in config.keys():
        config = config["db"]
    return next(iter(config.items())) if len(config) == 1 else config
