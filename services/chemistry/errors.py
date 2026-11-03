class ChemistryError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code

    def payload(self) -> dict:
        return {"code": self.code, "message": self.message}
