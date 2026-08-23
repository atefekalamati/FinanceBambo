"""Import invariants that both the service and its repository have to answer to."""

from .errors import FinanceDomainError


class DuplicateImportFile(FinanceDomainError):
    """The same bytes were already committed for this project and import kind.

    Identity is the file's SHA-256, not its name: a renamed copy is the same import.
    Changing a single cell changes the digest, so a corrected file is a new import and
    goes through untouched.
    """

    status = 409
    code = "DUPLICATE_IMPORT_FILE"
