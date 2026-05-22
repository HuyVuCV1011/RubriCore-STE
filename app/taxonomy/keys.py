from enum import Enum


class AssessmentTypeKey(str, Enum):
    MULTIPLE_CHOICE = "multiple-choice"
    NUMERIC_ANSWER = "numeric-answer"
    SHORT_ANSWER = "short-answer"
    CONSTRUCTED_RESPONSE = "constructed-response"
    CODE_ASSIGNMENT = "code-assignment"
    PROJECT = "project"
    LAB_REPORT = "lab-report"
    ORAL_EXPLANATION = "oral-explanation"
    VISUAL_CRITIQUE = "visual-critique"
    MIXED_FORMAT = "mixed-format"


class EvidenceTypeKey(str, Enum):
    TEXT = "text"
    NUMERIC = "numeric"
    SELECTED_OPTION = "selected-option"
    FILE_ARTIFACT = "file-artifact"
    CODE = "code"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    TABLE = "table"
    NOTEBOOK = "notebook"
    ARCHIVE = "archive"
    MIXED_BUNDLE = "mixed-bundle"


class OutputTypeKey(str, Enum):
    EXACT_ANSWER = "exact-answer"
    SELECTED_OPTION = "selected-option"
    NUMERIC_VALUE = "numeric-value"
    NUMERIC_VALUE_WITH_UNIT = "numeric-value-with-unit"
    SHORT_TEXT = "short-text"
    LONG_TEXT = "long-text"
    STRUCTURED_EXPLANATION = "structured-explanation"
    EXECUTABLE_BEHAVIOR = "executable-behavior"
    CODE_OUTPUT = "code-output"
    FILE_ARTIFACT = "file-artifact"
    VISUAL_ARTIFACT = "visual-artifact"
    TABULAR_RESULT = "tabular-result"
    REPORT = "report"
    PRESENTATION = "presentation"
    MIXED_OUTPUT = "mixed-output"


class RubricTypeKey(str, Enum):
    BINARY_KEY = "binary-key"
    CHECKLIST = "checklist"
    ANALYTIC_RUBRIC = "analytic-rubric"
    HOLISTIC_RUBRIC = "holistic-rubric"
    CRITERION_WEIGHTED_RUBRIC = "criterion-weighted-rubric"


class DeterminismLevel(str, Enum):
    DETERMINISTIC = "deterministic"
    MOSTLY_DETERMINISTIC = "mostly-deterministic"
    HYBRID = "hybrid"
    JUDGMENT_BASED = "judgment-based"


class AmbiguityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"
