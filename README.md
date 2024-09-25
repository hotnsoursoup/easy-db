# easy-db

[![PyPI - Version](https://img.shields.io/pypi/v/easy-db.svg)](https://pypi.org/project/easy-db)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/easy-db.svg)](https://pypi.org/project/easy-db)

-----
1. [Introduction](#introduction)
   1. [Key Features](#key-features)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
   1. [Executing queries with parameters](#executing-queries-with-parameters)
   2. [Calling stored procedures](#calling-stored-procedures)
   3. [Using offset and page_size](#using-offset-and-page_size)
   4. [Using fetch](#using-fetch)
4. [Configuration File Models](#configuration-file-models)
   1. [Single Database Model](#single-database-model)
   2. [Available Configuration Options](#available-configuration-options)
   3. [Paging Configuration](#paging-configuration)
   4. [MultiDatabaseModel](#multidatabasemodel)
5. [Handlers and Methods](#handlers-and-methods)
   1. [Execution flow handlers](#execution-flow-handlers-basedatabaseconnection)
6. [SqlAlchemyConnection](#sqlalchemyconnection)
   1. [Sessions and Scoped sessions](#sessions-and-scoped-sessions)
7. [Background](#background)
8. [License](#license)


# Introduction

This library provides a lightweight and simple way of creating database connection objects using configuration files with a few extras for pre-processing (sanitizing inputs, adding in paging, generating stored procedure queries), execution handling, and post processing.

### Key Features:
- **Flexible Configurations**: Supports single and multi-database configurations.
- **Pydantic Validation**: Ensures configuration accuracy using Pydantic models.
- **Raw SQL Support**: Currently only supports direct execution of raw SQL queries, with ORM integration planned for future versions.
- ** *test * **: teds
- **Extensibility**: Allows for the addition of custom handlers for pre and post execution processing, error handling, and more.

## Installation

```console
pip install easy-db
```

# Quick Start

Here’s a quick example of setting up a database connection using a configuration file:

```yaml
# yaml configuration file
dialect: mysql
uri: "mysql+pymysql://user:pass@localhost:3306/mysql"
```
Alternative configuration file using pyaml_env to import environment variables.
```yaml
dialect: mysql
connection_params:
   driver: mysql+mysqldb
   host: localhost
   user: !ENV {DB_USER}
   password: !ENV {DB_PASSWORD}
```


A shorthand import of the sqlalchemy connection.
```python
from easy-db import db
```

Full import with alias.

```python
from easy-db import SqlAlchemyConnection as connection
```

Creating the connection and executing the query. 


```python

from pyaml_env import parse_config

config_file = "\path\to\config.yaml"
config = parse_yaml(config_file)

# Load the connection using the configuration file
db = connection(config)

# Execute a raw SQL query
query = "select * from mytable"

# A connection is made when execute is run.
result = db.execute(query)

# If you want to connect prior to executing, you can do this.
db.connect()

# You can use context managers too
with db.connect() as conn:
   conn.execute(query)
```

### Executing queries with parameters

The library uses sqlalchemy's text(query) function to protect against injection
attacks. Queries with parameters that need to be formatted must use **:variable**
to identify the variable to be formatted.

```python
# Params must be a dictionary/mapping

params = {"id": "1"}
query = "select * from mytable where id = :id"
result = db.execute(query, params)
```

Or you can use tuples for the values. Note the use of IN.

```python
query = "select * from mytable where id IN :id"
params = {"id": (1, 2, 3)}

result = db.execute(query, params)
```
### Calling stored procedures

Calling execute_sp with the name of the stored procedure will generate the 
sql query for the dialect selected. There is no paging capability, but you can
still fetch results from the result object. (see below)

```python
procedure_name = "my_procedure"

result = db.execute_sp(procedure_name, params)
```

If a database is not specified in the connection, you must use {database}.{procedure_name} to identify the procedure. 

```python
procedure_name = "dbo.my_procedure"
```

### Using offset and page_size

Page size can be set in the config file to set a default page_size for **all** requests or can be passed into execute to override the default. This will automatically add in page_size for all raw sql passed into execute. 

```python

# Can be set on the instance or set in the configuration for ALL instances.
db.page_size = 10
offset = 50
page_size = 30

# Will return 30 results starting at offset 50 from the query
result = db.execute(query, params, offset, page_size)

```

### Using fetch
Fetch is used for post execution retrieval of the results. Fetch may not be available
if you have created a subclass of BaseDatabaseConnection and your connection object does not support it.
When using fetch, it will always return a tuple - the data and the result object. This is
to ensure you have access to continue fetching any rows that may still exist on the result object. 

```python
data = db.execute(query, args, fetch=50)
```
Setting the fetch_return in the config or setting it on the instance can control
the behavior of the fetch result. This can be set to "data, "object", or "tuple". 

yaml

```yaml
# yaml
fetch_return: tuple
```

```python
# python
db.fetch_return = "tuple"
data, result_object = db.execute(query, args, fetch=50)

more_data = result_object.fetchmany(10)
```

The result object is also accessible via connection.ro or connection.result_object.

You can also use the fetch method on the result object to fetch more results from the result object.

```python
data = db.execute(query, args, fetch=50)

fetched_results = db.ro.fetchall()
```
or using the fetch method of the connection will automatically fetch from the current 
result object for that instance (if it exists)

```python
while db.ro.rowcount > 0:

   fetched_data = db.fetch(5)

   myfunc(fetched_data)
```


# Configuration File Models

The configuration models are models that ensure that your configuration is set
correctly to function properly with the connection. There are currently two models - a single database or a multidatabase config.

Examples shown are using the SqlAlchemyConnection class object.

### Single Database Model

* **Required Fields:**
    * **For SQLite:**
        * `path`: Specify the path to your SQLite database file.
    * **For Other Dialects:**
        * `dialect`: Specify the database dialect (e.g., "mysql", "postgresql", "sqlite").
        * Either `uri` (connection string) or `params` (connection parameters) must be provided. If both are present, `uri` will take precedence.
* **Dialect Drivers:**
    * **Description:**  
      Each supported dialect comes with its associated driver string.
    
    * **Default Drivers:**
    
      | Dialect     | Connection String          |
      |-------------|----------------------------|
      | postgresql  | postgresql+psycopg2         |
      | mysql       | mysql+pymysql               |
      | sqlite      | sqlite                      |
      | oracle      | oracle+cx_oracle            |
      | mssql       | mssql+pymssql               |

* **ODBC Connections:**
    * If `use_odbc` is set to `True`, you must also specify the `driver`.


Example while using uri (connection string):

```yaml
# uri format: {driver}://{user}:{password}@{host}:{port}/{database}
dialect: mysql
uri: "mysql+pymysql://user:pass@localhost:3306/mysql"
paging:
   enabled: True
   page_size: 30
```

Example with connection parameters:

```yaml
dialect: mysql
connection_params:
   driver: mysql+mysqldb
   host: localhost
   user: myuserid
   password: mypass1
   database: mydatabase
   options:
      pool_size: 20
      pool_timeout: 30
fetch_return: data
```

Sqlite database
 
```yaml
dialect: sqlite
path: mysqlitedb.db
```

### Available Configuration Options.

Note - some are not yet be implemented (such as odbc and orm)

| Field           | Type                                      | Required | Description                                                                 | Development Notes                     |
|-----------------|-------------------------------------------|----------|-----------------------------------------------------------------------------|---------------------------------------|
| `description`   | `Optional[str]`                           | No       | A brief description of the database connection.                             | Used for documentation or metadata.   |
| `default`       | `Optional[bool]`                          | No       | Marks this as the default connection. Default: `False`.                     | Set to `True` if this is the default connection. |
| `dialect`       | `Literal["mysql", "mariadb", "mssql", "postgresql", "oracle", "sqlite"]` | Yes      | The database dialect to use.                                                | Required to specify the database type. |
| `use_odbc`      | `Optional[bool]`                          | No       | Enable ODBC support. Default: `False`.                                      | Set this to `True` when using ODBC connections. |
| `uri`           | `Optional[str]`                           | No       | Connection string (for SQL Alchemy or ODBC).                                | Use either `uri` or `params` (but not both). |
| `connection`    | `Optional[ConnectionParams]`              | No       | Connection parameters (host, username, etc.).                               | Alternative to `uri` for defining connection details. |
| `auto_commit`   | `Optional[bool]`                          | No       | Automatically commit transactions. Default: `False`.                        | Set to `True` for autocommit mode. |
| `path`          | `Optional[str]`                           | Only for SQLite | The path to the SQLite database file.                                       | Required when using the SQLite dialect. |
| `page_size`     | `Optional[int]`                           | No       | The number of results per page when querying.                               | Helps manage query result pagination. |

### Connection Parameters

| Field    | Type              | Description                                                                 | Development Notes                     |
|----------|-------------------|-----------------------------------------------------------------------------|---------------------------------------|
| `driver` | `Optional[str]`    | The driver to use with the connection.                                      | Needed for ODBC or certain dialects.  |
| `host`   | `Optional[str]`    | The database host.                                                          | Required for non-ODBC connections.    |
| `port`   | `Optional[int]`    | The port number for the database connection.                                | Standard ports apply, e.g., 3306 for MySQL. |
| `user` | `Optional[str]`  | The username for database authentication.                                   | Must match the database credentials.  |
| `password` | `Optional[str]`  | The password for database authentication.                                   | Required for most connections except SQLite. |
| `options` | `Optional[Dict[str, str]]` | Additional options to pass to the connection.                       | Key-value pairs for extra connection parameters. |

### Paging Configuration

| Field           | Type              | Default | Description                                                                 | Development Notes                     |
|-----------------|-------------------|---------|-----------------------------------------------------------------------------|---------------------------------------|
| `enabled`       | `Optional[bool]`  | `False`  | Whether paging is enabled.                                                  | Enable paging for each request.                |
| `page_size`     | `int`             |         | Number of results per page.                                                 | Used to limit the number of rows per query. |
| `min_page_size` | `Optional[int]`   | `0`     | Minimum number of results before paging begins.                             | Useful for performance optimization and mininum result length before paging is enabled. ** not implemented |

### MultiDatabaseModel

This model supports configurations for multiple databases. Each database is represented by a key in the configuration file and the value is a single database model (BaseDatabaseModel). 

Example:
```yaml
mydefaultdatabase:
   dialect: mysql
   default: True
   connection_params:
      driver: mysql+mysqldb
      host: localhost
      user: myuserid
      password: mypass1
      database: mydatabase
      options:
         pool_size: 20
         pool_timeout: 30
   fetch_return: data
myloggingdb:
   dialect: sqlite
   path: mysqlitedb.db
```

The SqlAlchemyConnection supports multiple databases, though it does not have
the capability to bind (yet). If a MultidatabaseModel config is used, one of
these scenarios will occur.

```python
from easy-db import SqlAlchemyConnection as connection

# A name (key) is used to select the database
db = connection(config=config, name='mydatabase1')

# name is not provided and the config is multi database 
db = connection(config)
```

When a name is not supplied, the order of operations looks for:

1. A **default** key with a value of **True**.
   - The model validation ensures only 1 can be set to default
2. A default config assigned to the class.
   - db.default_config
   - _config = self.default_config
3. A default config **name** assigned to the class
   - db.default_config_name
   - _config = config[default_config_name]
4. The first database in the config

# Handlers and Methods

This library provides a few accessible ways for you to control parameter pre-processing, execution control, and result processing. You may want to validate parameters, create a subclass and use a different execution method, and/or serialize any time data using result handlers. The order of handlers listed follows order below. 

### Execution flow handlers (BaseDatabaseConnection)

| Handler/method    | Type       |Description                                      |  Notes            |
|-----------------|---------------|-------------------------------------------------|------------------------------|
| sanitizers | Callable \| List[Callable] | A callable function to sanitize input parameters for sql queries. | 
| execution_handler | Callable | A handler to override the execution of the query to obtain the result_object | May improve to be able to override 
| data_processors | List[Callable] | Processes the data after execution/fetch. It will iterate through and run each handler in order | You can use cls.add_process_handler(handlers) to add additional handlers. It can me a list of handlers or just one handler.
| error_handler | Callable | A handler to manage errors, does not handle errors with current version. | Currently a method for the class, but subclassing.
| logging_handler | Callable | A handler that uses a config to control log events and log destination. | ** NOT IMPLEMENTED **


# SqlAlchemyConnection

SqlAlchemyConnection is the primary connection object of the library. It is a subclass of the BaseDatabaseConnection with methods for session management. The input args provide flexibility in configuring the type of connection or session you may want to use. 

| argument   | Type       | default | Description                                      |  Notes            |
|-----------------|-------|--------|-------------------------------------------------|------------------------------|
| config | Dict |  | The database configuration | 
| name | Str | None | For multidatabase models, the name (key) of the database connection configuration
| connect | Bool | False |If True, automatically connect when the object is created |
| use_session | Bool | True | Creates the SqlAlchemy connection using sessionmaker(bind=self.engine) | 
| use_scoped_session | Bool | False | Creates the SqlAlchemy connection using scoped_session(sessionmaker(bind=self.engine)) | If somehow both session and scoped session are True, scoped session will take precendence. 


## Sessions and Scoped sessions
Example of creating a scoped session (if you want thread safety).

```python
from easy-db import db
from pyaml_env import parse_config

config_file = "\path\to\config.yaml"
config = parse_config(config_file)

# Create the connection using scoped session
connection = db(config, use_scoped_session=True)

connection.execute("select * from users")

```

**NOTE** - When both session and scoped_session are False, the connection simply returns engine.connect().

### New sessions from the same sessionmaker

If you want to create additional sessions from the same sessionmaker, you simply call Session() on the connection. This creates a new object with the same reference to the original sessionmaker.

```python
new_session = connection.Session()

new_session.execute(query)
```
## License

`easy-db` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
