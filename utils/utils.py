from warnings import warn
from typing import Any


def get_dict_value(key: str, dictionary: dict, default_value: str = "") -> Any:
    "Retrieve dictionary values with the existence of tuples as keys"
    if dictionary and isinstance(dictionary, dict):
        if any(isinstance(k, tuple) for k in dictionary):
            for k, v in dictionary.items():
                if key in k:
                    return v if v else default_value
        else:
            return dictionary.get(key, default_value)
    else:
        return default_value


def flatten_str(message: str) -> str:
    "Removes line breaks and excess spaces from the string"
    return " ".join(message.split())


def warn(message: str) -> str:
    "Flattens input string and issues warning"
    warn(flatten_str(message), stacklevel=3)
