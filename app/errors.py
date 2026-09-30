class ApiError(Exception):
    """Raised anywhere in the app; rendered as {"error": message}."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)
