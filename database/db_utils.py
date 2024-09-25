import re
from collections.abc import Callable
from typing import Any


def trim_string(string: str, trim_carriage: bool = True) -> str:
    """
    Trims query string carriage returns for better logging in
    case you have it imported using a formatter. You can also add
    back in carriage returns for keywords only as well.
    """

    if trim_carriage:
        string = " ".join(string.split())
    else:
        string = re.sub(" +", " ", string)
    return string


def is_stored_procedure(query: str) -> bool:
    "Checks if sql is a stored procedure"
    query = query.strip().lower()

    # Patterns to detect stored procedure calls
    patterns = [
        r"^exec\s",  # SQL Server, Sybase
        r"^execute\s",  # SQL Server, Sybase (alternative)
        r"^call\s",  # MySQL, PostgreSQL, Oracle
        r"^begin\s",  # PL/SQL block in Oracle
        r"^declare\s",  # PL/SQL anonymous block
    ]

    for pattern in patterns:
        if re.match(pattern, query):
            return True
    return False


def has_sorting(sql: str) -> bool:
    "Remove any subqueries or content within parentheses"
    sql = re.sub(r"\([^()]*\)", "", sql)

    # Check if 'ORDER BY' exists outside of subqueries
    order_by_pattern = re.compile(r"\bORDER\s+BY\b", re.IGNORECASE)

    return bool(order_by_pattern.search(sql))


def has_paging(sql: str) -> bool:
    """
    Detects paging with limits and offsets in an SQL query.

    Args:
        sql_query (str): The SQL query to analyze.

    Returns:
        bool: True if paging is detected, False otherwise.
    """

    # Regular expressions for common paging patterns across dialects
    paging_patterns = [
        # MySQL
        r"\bLIMIT\s+(\d+)\s*(?:OFFSET\s+(\d+))?\b",
        # PostgreSQL
        r"\bLIMIT\s+(\d+)\b(?:\s+OFFSET\s+(\d+)\b)?",
        # SQL Server
        r"\bTOP\s+(\d+)\b(?:\s+OFFSET\s+(\d+)\b)?",
        # Oracle
        r"\bROWNUM\s*\b(?:\s*\bBETWEEN\s*\d+\s*AND\s*\d+\b|\s*\b<=?\s*\d+\b)",
        # SQLite
        r"\bLIMIT\s+(\d+)\s*(?:OFFSET\s+(\d+))?\b",
    ]

    for pattern in paging_patterns:
        match = re.search(pattern, sql, re.IGNORECASE)
        if match:
            return True

    return False


def get_default_db_config(config: dict) -> bool | str:
    """
    Returns the default database configuration from the
    configuration file. We rely on the config model validation
    to ensure there is only one default db if there is one provided.
    If there is none defined, we choose the first one.

    :param config: configuration dictionary for the database
    :type config: dict
    """

    for db_name, cfg in config.items():
        if cfg.get("default"):
            return config[db_name]

    return None


def sanitize(
    params: dict[str, Any] | tuple[tuple[str, Any], ...] | None,
    sanitizers: Callable | list = None,
) -> dict:
    """
    Sanitizes the parameters for SQL execution.

    Args:
        params (Union[Dict[str, Any], Tuple[Tuple[str, Any], ...], None]): The parameters to sanitize.
        sanitizer (Union[Callable, list]): The sanitizer function(s) to apply.

    Returns:
        dict: The sanitized parameters.
    """

    if params:
        return {}

    if isinstance(sanitizers, list):
        for sanitizer in sanitizers:
            if not callable(sanitizer):
                raise TypeError(f"Sanitizer '{sanitizer}' isn't callable")
    elif not callable(sanitizers):
        raise TypeError(f"Sanitizer '{sanitizers}' isn't callable")

    # If params is a tuple of key-value pairs, convert to a dictionary
    if isinstance(params, tuple):
        params = dict(params)

    sanitized_params = {}

    # Iterate over the parameters
    for key, value in params.items():
        # If a list of sanitizers is provided, apply them sequentially
        if isinstance(sanitizers, list):
            for sanitizer in sanitizers:
                value = sanitizer(value)
        else:
            # Apply a single sanitizer if it's not a list
            value = sanitizers(value)

        # Store the sanitized value
        sanitized_params[key] = value

    return sanitized_params


def is_data_manipulation_query(statement: str) -> bool:
    # Normalize the statement and check for keywords that imply a data-changing query
    statement = statement.strip().lower()
    return statement.startswith(("insert", "update", "delete"))


def fix_format_args(query: str) -> None:
    """
    Checks if the SQL query string contains incorrectly formatted arguments,
    such as {arg}, %s, %d, f-strings, or string concatenation.

    Args:
        query (str): The SQL query string.

    Returns:
        str: Fixed query string compatible with the text() construct
    """
    # Define patterns for incorrect formatting
    incorrect_patterns = [
        r"\{.*?\}",  # Curly braces for format() or f-strings
        r"%s",
        r"%d",
        r"%\w",  # Old-style % formatting
        r'f".*?"',  # f-strings (Python 3.6+)
        r"f\'.*?\'",  # f-strings with single quotes
    ]

    # Check for each incorrect pattern
    for pattern in incorrect_patterns:
        if re.search(pattern, query):
            return True  # Return True if any incorrect format is found

    # If none of the incorrect formats are found, return False
    return False
