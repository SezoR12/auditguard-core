import enum


class UserRole(str, enum.Enum):
    owner = "owner"
    gm = "gm"
    manager = "manager"
    auditor = "auditor"
    admin = "admin"
    appowner = "appowner"


class CompanyTier(str, enum.Enum):
    essential = "essential"
    advanced = "advanced"
    elite = "elite"


class TaskType(str, enum.Enum):
    document_review = "document_review"
    field_visit = "field_visit"
    reconciliation = "reconciliation"
    investigation = "investigation"
    other = "other"


class TaskStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    overdue = "overdue"


class FileType(str, enum.Enum):
    excel = "excel"
    csv = "csv"
    word = "word"
    image = "image"
    pdf = "pdf"
    encrypted_json = "encrypted_json"


class DocCategory(str, enum.Enum):
    invoice = "invoice"
    receipt = "receipt"
    contract = "contract"
    report = "report"
    statement = "statement"
    other = "other"


class DocStatus(str, enum.Enum):
    pending = "pending"
    ocr_processing = "ocr_processing"
    certified = "certified"


class LedgerAction(str, enum.Enum):
    insert = "insert"
    update = "update"
    delete = "delete"
    reverse = "reverse"


class OutputType(str, enum.Enum):
    dashboard = "dashboard"
    report = "report"
    trust_index = "trust_index"
    summary = "summary"
    prediction = "prediction"
    narrative = "narrative"
    daily_snapshot = "daily_snapshot"


class WasteCategory(str, enum.Enum):
    financial = "financial"
    operational = "operational"
    human = "human"
    opportunity = "opportunity"


class Severity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"
