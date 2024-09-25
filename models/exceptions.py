class ModelValidationErrors(Exception):
    """Custom exception to capture and display errors from multiple models."""

    def __init__(self, model_errors: dict[str, list[dict]]):
        """
        :param model_errors: Dictionary where the keys are model names and
                             values are lists of dictionaries containing:
                             - 'score': the model match score
                             - 'errors': the list of error dictionaries.
        """
        self.model_errors = model_errors
        super().__init__(self._generate_message())

    def _generate_message(self) -> str:
        """
        Creates an error message that provides the model, the match score
        and the error message for each model.
        """

        messages = []
        for model_name, error_dicts in self.model_errors.items():
            error_message = [f"Model: '{model_name}':"]
            # Use a score to determine how closely it matches a model.
            for error in error_dicts:
                # Get error location
                loc = " -> ".join(map(str, error["loc"]))
                location = f"{loc if loc else 'Root'}"

                # Get error message
                msg = error["msg"].split(",")[1]
                type = error["msg"].split(",")[0]

                error_message.append(f"\n - Location: {location}")
                error_message.append(f" - Error: {type}:")
                error_message.append(f"  -{msg}")

            messages.append("\n".join(error_message))
        return "\n\n".join(messages)
