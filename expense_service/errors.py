class AppError(Exception):
    def __init__(self, status, error, message):
        super().__init__(message)
        self.status = status
        self.error = error
        self.message = message