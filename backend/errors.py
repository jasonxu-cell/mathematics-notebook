class RequestError(Exception):
    """A protocol error with a stable, user-visible classification."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
