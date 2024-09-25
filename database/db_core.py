import warnings
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.engine import (
    Connection,
    Engine,
    Result,
)
from sqlalchemy.orm import (
    Session,
    scoped_session,
    sessionmaker,
)

from database.db_utils import (
    get_default_db_config,
    has_paging,
    is_data_manipulation_query,
    sanitize,
)
from models.db_model import validate_db_model


# Supported database drivers
drivers = {
    "postgresql": "postgresql+psycopg2",
    "mysql": "mysql+pymysql",
    "sqlite": "sqlite",
    "oracle": "oracle+cx_oracle",
    "mssql": "mssql+pymssql",
}


error_messages = {
    "missing_params": "Please check your configuration file. Missing connection information.",
    "missing_type": "A connection string requires a type: odbc, dsn, sqlalchemy",
    "missing_dialect": "Please check your configuration file. A valid dialect or connection string is required.",
    "invalid_connector": "Invalid connector specified. Only sqlalchemy, odbc, and dsn are allowed.",
    "missing_connector_with_uri": "A valid connector is required when using a connection string.",
    "missing_db_config": "Please check your configuration file for a valid database entry.",
    "named_db_not_found": "The named database configuration was not found in the configuration file.",
    "operational_error:": "Operational error: Failed to connect to the database. Details: {}",
    "unsupported_dialect": "The database dialect is not supported. Please refer to documentation for supported dialects.",
    "key_error": "Please check your configuration file for a valid database entry.",
    "validation_error": "The config does not match the model. Please refer to wiki.",
    "invalid_fetch": "Fetch value must be an int. Use 0 for all rows",
    "paging_error": "Paging is enabled but page_size is missing or set to 0",
}


class BaseDatabaseConnection(ABC):
    """
    Default database configuration used when one is not defined. This
    is more for use when you have multiple database configurations.
    """

    default_config = None
    default_config_name = None

    """
    ORM support is not currently available, but is in roadmap. 
    """
    orm = False

    "Handles __exit__ if the connection doesn't support context management"
    exit = None

    def __init__(
        self, config: dict, name: str = None, methods: dict[str, Callable] = None
    ):
        """
        The BaseDatabaseConfig class serves as an abstract base class that
        provides a standardized configuration framework for connecting to
        various database systems.

        Key Features:

        SqlAlchemy engine via config.
            The configuration will generate the uri, add engine options,
            and create/manage the connection.

        Better raw sql support.
            Raw sql is not the recommended implementation, nor is stored
            procedure, but there may be use cases. This class allows for
            sql query and parameter construction, sorting, pagination,
            error handling, and more.

            Subclass and use execute. Within execute, call self._execute_query

            class MyDbClass(BaseDatabaseModel):

            def connect(self):

                my_connection = #Your connection method here

                self.connection = my_connection

                return self.conn

            def execute(self, sql, params):

                #do things

                self._execute_query(sql, params)


        Stored procedure execution by name.
            The stored procedure logic will generate a procedure based
            on dialect of the database. Note, you may have to prefix
            your stored procedure with your database (e.g. dbo.my_procedure)

            MySubClass.execute_stored_procedure(name, params)

        sort:
            Sort logic can be applied by subclass and defining sort

        pagination:
            Will page results based on page size. You can set automatic
            paging for all routes through the configuration including
            the default behavior. Paging for separate routes can be
            configured within the route configuration.

            For global sort settings in config, see example below.
            0 or no setting defined will mean its disabled. Route
            definitions will override these. See documentation for more
            details.

            This will paginate for every 20 results if the total results
            exceed 30.

            settings:
                paging:
                    auto_page_size: 20
                    min_page_size: 30
            ------------------------------------------------------------



        :param dict config: The database configuration
        :param str name: The name (key) of the db to be used
        :param methods Dict[str, Callable] methods: A dictionary of methods
            you want to register to the instance class. Object class
            registrations have to be called explicitly.
            --> objclass.register_class_methods(methods)

        """
        # Useful in case you may want to pass in a MultiDatabaseModel
        # model -> see models/db_model
        self.config = config
        self.connection = None
        self.name = name
        self.result_obj = None
        # Pyndantic model validation. We rename config to still have a
        # reference to the original config. The validation will also
        # assign all default values not assigned in the config.

        try:
            model = self.model = validate_db_model(config)
            _config = self._config = model.model_dump()
        except ValidationError as e:
            raise e

        # If you have a multidatabase configuration and you have passed it to
        # the database model, you can call the specific configuration by name
        if model.__class__.__name__ == "MultiDatabaseModel":
            try:
                if name is not None:
                    _config = _config["name"]
                elif get_default_db_config(_config) is not None:
                    _config = get_default_db_config(_config)
                elif self.default_config is not None:
                    _config = self.default_config
                elif self.default_config_name is not None:
                    _config = _config[self.default_config_name]
                else:
                    _config = next(iter(_config.items()))
            except KeyError:
                raise KeyError("An invalid database name was supplied")

        self._config = _config
        # Set attributes from the config
        for key, value in _config.items():
            setattr(self, key, value)

        self.page_size = self.paging.get("page_size", 0)

        # To control execution of sql
        self.execution_handler = None
        # For post execution data
        self.data_processors = []
        # To manage successful execution messages
        self._success_handler = None
        # Sets connection options/args to pass into any connect() method
        if self.connection_params is not None:
            self.options = self.connection_params.get("options", {})
        else:
            self.options = {}
        # Placeholder for future functionality to control handler execution
        # self.process_code

        # Optional, Register methods to the class. We only process instance
        # methods for the init. Class instance methods should be handled
        # seperately from the class instance.
        if methods is not None:
            self.register_instance_methods(methods)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self.connection, "__exit__"):
            return self.connection.__exit__(exc_type, exc_val, exc_tb)
        else:
            self._exit(exc_type, exc_val, exc_tb)

    def _exit(self, exc_type, exc_val, exc_tb) -> None:
        """Custom cleanup logic in case the connection object lacks context management."""
        if exc_type is not None:
            if self.exit is not None:
                self.exit(exc_type, exc_val, exc_tb)
            else:
                warnings.warn("No exit method defined for the connection object.")
                self.close()
        else:
            # Commit or clean up resources normally
            print("No exception, cleaning up normally.")

    @property
    def ro(self) -> Result:
        "Shortcut for the result object if the connection supports it"
        return self.result_object

    @property
    def conn(self) -> Connection:
        return self.connection

    def execute_sp(
        self,
        procedure_name: str,
        params: dict[str, Any] | None = None,
        fetch: int = 0,
    ) -> dict | list:
        """Executes a stored procedure with the given parameters.

        :param procedure_name: The name of the stored procedure to call.
        :type procedure_name: str
        :param _params: A dictionary of parameter names and values (optional).
        :type _params: dict[str, Any] | None, optional

        :raises ValueError: If the database dialect is not supported.
        """

        dialect = self.dialect

        if dialect == "sqlite":
            raise ValueError("SQLite does not support stored procedures.")

        # SQL templates based on dialect
        sql_templates = {
            "postgresql": f"CALL {procedure_name}({', '.join([f':{key}' for key in params]) if params else ''})",
            "mysql": f"CALL {procedure_name}({', '.join([f':{key}' for key in params]) if params else ''})",
            "mssql": f"EXEC {procedure_name} {', '.join([f'@{key}=:{key}' for key in params]) if params else ''}",
            "oracle": f"BEGIN {procedure_name}({', '.join([f':{key}' for key in params]) if params else ''}); END;",
        }

        if dialect not in sql_templates:
            raise ValueError("Unsupported database dialect")

        # Select the appropriate procedure template
        query = sql_templates[dialect]

        return self._execute_query(query=query, params=params, fetch=fetch)

    def execute(
        self,
        query: str,
        params: dict[str, Any] | tuple[str] | None = None,
        fetch: int = 0,
        offset: int = 0,
        page_size: int = None,
    ) -> dict[str, str] | list[dict[str, str]]:
        "Override this if you want to provide custom logic"

        if not self.orm:
            return self._execute_query(query, params, fetch, offset, page_size)

    def add_result_handler(self, handlers: list[Callable] | Callable) -> None:
        "Add handlerss for the data returned from execution"
        if isinstance(handlers, list):
            for handler in handlers:
                if not callable(handler):
                    raise TypeError("Handler must be callable")
        self.data_processors.append(handlers)

    def register_instance_methods(self, methods: dict[str, Callable] = None) -> None:
        "Registers instance methods"
        for name, method in methods.items():
            if callable(method):
                setattr(self, name, method)
            else:
                raise TypeError(f"{name} is not callable")

    @classmethod
    def register_class_methods(cls, methods: dict[str, Callable]):
        "Registers class methods"

        for name, method in methods.items():
            if callable(method):
                setattr(cls, name, method)
            else:
                raise TypeError(f"{name} is not callable")

    def page(self, query: str, offset: int = 0, page_size: int | None = None) -> str:
        """
        Adds paging with limits and offsets to an SQL query based on the dialect.
        Please keep in mind that this capability may not function properly
        depending on database version you are using. (Oracle requires 12c+)

        Args:
            sql (str): The original SQL query.
            offset (int): The number of records to skip before starting to return the records.
            page_size (int): The number of records to limit the results.

        Returns:
            str: The SQL query with paging added.
        """

        query = query.strip()

        if has_paging(query):
            return query

        page_size = page_size if page_size else self.page_size

        if page_size == 0:
            return ValueError(error_messages["paging_error"])

        if self.dialect in ["mysql", "postgres", "sqlite"]:
            return f"{query} LIMIT {page_size} OFFSET {offset}"
        elif self.dialect in ["sql server", "oracle"]:
            return f"{query} OFFSET {offset} ROWS FETCH NEXT {page_size} ROWS ONLY"
        else:
            raise ValueError("Unsupported database dialect for paging.")

    @classmethod
    def set_page_size(cls, page_size: int) -> None:
        "A class method to set the page size for all class instances."
        if isinstance(page_size, int):
            cls.page_size = page_size
        else:
            raise ValueError("Page size must be an int.")

    def commit(self) -> None:
        if self.connection is not None:
            self.connection.commit()

    def close(self) -> None:
        """
        Handles the closing of the connection. Subclass and override
        if conn.close() is not supported by the connector
        """
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def fetch(self, result: Result = None, fetch: int = 0) -> dict[str, Any] | list:
        "Fetches the results from the result"

        result = result if result else self.result_object

        if result is None:
            raise ValueError("No valid result object found.")

        if isinstance(fetch, int):
            if fetch == 0:
                return result.fetchall()
            elif fetch == 1:
                return result.fetchone()
            return result.fetchmany(fetch)
        else:
            raise ValueError(error_messages["invalid_fetch"])

    def offset(self, query: str, offset: int) -> str:
        if self.dialect in ["mysql", "postgres", "sqlite"]:
            return f"{query} LIMIT ALL OFFSET {offset}"
        elif self.dialect in ["sql server", "oracle"]:
            return f"{query} OFFSET {offset} ROWS FETCH NEXT ALL ROWS ONLY"
        else:
            raise ValueError("Unsupported database dialect for paging.")

    def rollback(self) -> None:
        self.connection.rollback()

    def _execute_query(
        self,
        query: str,
        params: dict[str, Any] | tuple[str] | None = None,
        fetch: int = 0,
        offset: int = 0,
        page_size: int | None = None,
        sanitizers: Callable | list[Callable] = None,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """
        Executes a SQL query with optional parameters and pagination.
        """
        try:
            if not self.connection:
                self.connection = self.connect()

            _params = sanitize(params, sanitizers) if sanitizers else params

            # Handle pagination
            if page_size is not None or self.paging.get("enabled"):
                query = self.page(query=query, offset=offset, page_size=page_size)
            elif offset > 0:
                query = self.offset(query, offset)

            # Use a custom execution handler if one is provided
            if self.execution_handler is not None:
                result_obj = self.execution_handler(query, _params, fetch)
            else:
                # Executes the query with the connection
                result_obj = self.connection.execute(text(query), _params)

            # if fetch_return is set to data, you can still access the result
            # object to fetch more results.
            self.result_object = result_obj

            if not is_data_manipulation_query(query):
                # Fetch results
                data = self.fetch(result_obj, fetch)

                if fetch != 0:
                    if self.fetch_return == "object":
                        return result_obj
                    elif self.fetch_return == "tuple":
                        return self.process_data(data), result_obj
                return self.process_data(data)

            # Auto commit on write and not at the end of context.
            elif self.auto_commit:
                self.commit()

            # Manage success messages for data manipulation queries
            return self._success_handler(query)

        except Exception as e:
            return self.error_handler(e)

    def process_data(self, data: dict) -> dict:
        """
        Checks for a handlers, which will process results of the execution.
        Subclass override for processing query results. e.g. set default
        behavior for returning a single row as list or dict

        """
        if self.data_processors:
            for processor in self.data_processors:
                data = processor(data)
        return data

    def _success_handler(self, query: str) -> str:
        "Handles success messages"
        if self.success_handler:
            return self.success_handler()
        return {"message", "success"}

    def sort(self, query) -> str:
        "Override this if you want to provide sorting logic."
        return query

    def error_handler(self, error: Exception) -> Any:
        "Function to handle errors from execution. Implement as necessary"
        return error

    @abstractmethod
    def connect(self) -> Any:
        raise NotImplementedError("Subclasses must implement connect method.")

    def _read_sql_file(self):
        "For processing .sql files"

        # To be built


class SqlAlchemyConnection(BaseDatabaseConnection):
    def __init__(
        self,
        config: dict = None,
        name: str = None,
        connect: bool = False,
        use_session: bool = True,
        use_scoped_session: bool = False,
        session: Session = None,
    ):
        """
        Creates a SqlAlchmyDatabase object from a configuration file.
        Scoped sessions will override session. Use session.session if you
        are using sessions and want to access SqlAlchemy native commands.

        """

        super().__init__(config, name=name)

        self.use_session = use_session
        # Use scoped sessions if you want to manage lifecycle in a
        # multithreaded environment.
        self.use_scoped_session = use_scoped_session

        # Assign session if one is passed in
        self.session = session if session else None

        # Will automatically connect to the database on instantiation
        if connect or session is not None:
            self.connect()

    @property
    def engine(self) -> Engine:
        "Create a SQLAlchemy engine"
        engine_options = self.options if self.options else {}
        return create_engine(self._uri, **engine_options)

    @property
    def uri_base_string() -> str:
        "The base string for the connection uri"
        return "{driver}://{user}:{password}@{host}:{port}/{database}"

    def Session(self) -> Session:
        """
        Creates a new session based on the connection current configuration.
        This mimics a session factory by returning a new instance of
        SqlAlchemyConnection while passing in the session factory and config.
        """

        if self.session is None:
            raise ValueError("A session was never created. Use connect() first.")

        return SqlAlchemyConnection(
            config=self._config,
            name=self.name,
            use_session=self.use_session,
            use_scoped_session=self.use_scoped_session,
            session=self.session,
        )

    def connect(self) -> Connection:
        """Opens, sets, and returns the connection to the database."""

        if self.connection is not None:
            return self.connection

        # Creates a new session from the session factory.
        if self.session is not None:
            self.connection = self.session()

        if not self.use_session and not self.use_scoped_session:
            connection = self.connection = self.engine.connect()
        else:
            if self.use_scoped_session:
                self.session = scoped_session(sessionmaker(bind=self.engine))
            else:
                self.session = sessionmaker(bind=self.engine)
            connection = self.connection = self.session()

        return connection

    def close(self) -> None:
        if self.connnection is not None:
            if self.use_scoped_session:
                self.connection.remove()
            else:
                self.connection.close()
            self.connection = None

    @property
    def _uri(self) -> str:
        "Returns the connection string for create_engine"
        if self.uri:
            return self.uri
        return self.uri_base_string.format(**self.connection_params)
