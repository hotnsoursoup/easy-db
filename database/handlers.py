from datetime import date, datetime


class BaseHandler:
    def __init__(self, name: str, *args, **kwargs) -> None:
        self.name = name
        self.args = args
        self.kwargs = kwargs

    def handle(self, data: dict) -> dict:
        raise NotImplementedError("Subclasses must implement this method")


def time_serializer(data: dict, time_format: str) -> dict:
    """
    "Converts all time values to a string format"""
    for key, value in data.items():
        if isinstance(value, (datetime, date)):
            data[key] = value.strftime(time_format)
        elif isinstance(value, dict):
            data[key] = time_serializer(value, time_format)
    return


def single_row_converter(data: dict, dictionary=True) -> dict:
    """
    Handles a row of data, converting time values to a string format
    """
    if len(data) == 1:
        if isinstance(data, list) and dictionary:
            return data[0]
        elif isinstance(data, dict) and not dictionary:
            return [data]
    return data
