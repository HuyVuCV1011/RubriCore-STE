from app.taxonomy.keys import AssessmentTypeKey, EvidenceTypeKey, OutputTypeKey, RubricTypeKey


class TaxonomyCompatibilityError(ValueError):
    pass


COMPATIBLE_EVIDENCE_TYPES: dict[AssessmentTypeKey, set[EvidenceTypeKey]] = {
    AssessmentTypeKey.MULTIPLE_CHOICE: {EvidenceTypeKey.SELECTED_OPTION},
    AssessmentTypeKey.NUMERIC_ANSWER: {EvidenceTypeKey.NUMERIC, EvidenceTypeKey.TEXT},
    AssessmentTypeKey.SHORT_ANSWER: {EvidenceTypeKey.TEXT},
    AssessmentTypeKey.CONSTRUCTED_RESPONSE: {EvidenceTypeKey.TEXT, EvidenceTypeKey.FILE_ARTIFACT},
    AssessmentTypeKey.CODE_ASSIGNMENT: {EvidenceTypeKey.CODE, EvidenceTypeKey.FILE_ARTIFACT, EvidenceTypeKey.ARCHIVE},
    AssessmentTypeKey.PROJECT: {EvidenceTypeKey.MIXED_BUNDLE, EvidenceTypeKey.FILE_ARTIFACT, EvidenceTypeKey.ARCHIVE},
    AssessmentTypeKey.LAB_REPORT: {EvidenceTypeKey.TEXT, EvidenceTypeKey.FILE_ARTIFACT, EvidenceTypeKey.MIXED_BUNDLE},
    AssessmentTypeKey.ORAL_EXPLANATION: {EvidenceTypeKey.AUDIO, EvidenceTypeKey.VIDEO, EvidenceTypeKey.TEXT},
    AssessmentTypeKey.VISUAL_CRITIQUE: {EvidenceTypeKey.IMAGE, EvidenceTypeKey.TEXT, EvidenceTypeKey.MIXED_BUNDLE},
    AssessmentTypeKey.MIXED_FORMAT: set(EvidenceTypeKey),
}

COMPATIBLE_OUTPUT_TYPES: dict[AssessmentTypeKey, set[OutputTypeKey]] = {
    AssessmentTypeKey.MULTIPLE_CHOICE: {OutputTypeKey.SELECTED_OPTION, OutputTypeKey.EXACT_ANSWER},
    AssessmentTypeKey.NUMERIC_ANSWER: {OutputTypeKey.NUMERIC_VALUE, OutputTypeKey.NUMERIC_VALUE_WITH_UNIT},
    AssessmentTypeKey.SHORT_ANSWER: {OutputTypeKey.SHORT_TEXT, OutputTypeKey.EXACT_ANSWER},
    AssessmentTypeKey.CONSTRUCTED_RESPONSE: {OutputTypeKey.LONG_TEXT, OutputTypeKey.STRUCTURED_EXPLANATION},
    AssessmentTypeKey.CODE_ASSIGNMENT: {OutputTypeKey.EXECUTABLE_BEHAVIOR, OutputTypeKey.CODE_OUTPUT},
    AssessmentTypeKey.PROJECT: {OutputTypeKey.MIXED_OUTPUT, OutputTypeKey.FILE_ARTIFACT, OutputTypeKey.PRESENTATION},
    AssessmentTypeKey.LAB_REPORT: {OutputTypeKey.REPORT, OutputTypeKey.TABULAR_RESULT, OutputTypeKey.MIXED_OUTPUT},
    AssessmentTypeKey.ORAL_EXPLANATION: {OutputTypeKey.STRUCTURED_EXPLANATION, OutputTypeKey.LONG_TEXT},
    AssessmentTypeKey.VISUAL_CRITIQUE: {OutputTypeKey.VISUAL_ARTIFACT, OutputTypeKey.LONG_TEXT},
    AssessmentTypeKey.MIXED_FORMAT: set(OutputTypeKey),
}

COMPATIBLE_RUBRIC_TYPES: dict[AssessmentTypeKey, set[RubricTypeKey]] = {
    AssessmentTypeKey.MULTIPLE_CHOICE: {RubricTypeKey.BINARY_KEY},
    AssessmentTypeKey.NUMERIC_ANSWER: {RubricTypeKey.BINARY_KEY, RubricTypeKey.CHECKLIST},
    AssessmentTypeKey.SHORT_ANSWER: {RubricTypeKey.BINARY_KEY, RubricTypeKey.CHECKLIST, RubricTypeKey.ANALYTIC_RUBRIC},
    AssessmentTypeKey.CONSTRUCTED_RESPONSE: {
        RubricTypeKey.ANALYTIC_RUBRIC,
        RubricTypeKey.HOLISTIC_RUBRIC,
        RubricTypeKey.CRITERION_WEIGHTED_RUBRIC,
    },
    AssessmentTypeKey.CODE_ASSIGNMENT: {
        RubricTypeKey.CHECKLIST,
        RubricTypeKey.ANALYTIC_RUBRIC,
        RubricTypeKey.CRITERION_WEIGHTED_RUBRIC,
    },
    AssessmentTypeKey.PROJECT: {
        RubricTypeKey.CHECKLIST,
        RubricTypeKey.ANALYTIC_RUBRIC,
        RubricTypeKey.CRITERION_WEIGHTED_RUBRIC,
    },
    AssessmentTypeKey.LAB_REPORT: {RubricTypeKey.ANALYTIC_RUBRIC, RubricTypeKey.CRITERION_WEIGHTED_RUBRIC},
    AssessmentTypeKey.ORAL_EXPLANATION: {RubricTypeKey.ANALYTIC_RUBRIC, RubricTypeKey.HOLISTIC_RUBRIC},
    AssessmentTypeKey.VISUAL_CRITIQUE: {RubricTypeKey.ANALYTIC_RUBRIC, RubricTypeKey.HOLISTIC_RUBRIC},
    AssessmentTypeKey.MIXED_FORMAT: set(RubricTypeKey),
}


def _coerce(enum_type: type, value: str):
    try:
        return enum_type(value)
    except ValueError as exc:
        raise TaxonomyCompatibilityError(f"Unknown taxonomy value: {value}") from exc


def validate_taxonomy_combination(
    *,
    assessment_type: str,
    evidence_type: str | None = None,
    output_type: str | None = None,
    rubric_type: str | None = None,
) -> None:
    assessment_key = _coerce(AssessmentTypeKey, assessment_type)

    if evidence_type is not None:
        evidence_key = _coerce(EvidenceTypeKey, evidence_type)
        if evidence_key not in COMPATIBLE_EVIDENCE_TYPES[assessment_key]:
            raise TaxonomyCompatibilityError(
                f"Evidence type {evidence_key.value!r} is not compatible with "
                f"assessment type {assessment_key.value!r}."
            )

    if output_type is not None:
        output_key = _coerce(OutputTypeKey, output_type)
        if output_key not in COMPATIBLE_OUTPUT_TYPES[assessment_key]:
            raise TaxonomyCompatibilityError(
                f"Output type {output_key.value!r} is not compatible with "
                f"assessment type {assessment_key.value!r}."
            )

    if rubric_type is not None:
        rubric_key = _coerce(RubricTypeKey, rubric_type)
        if rubric_key not in COMPATIBLE_RUBRIC_TYPES[assessment_key]:
            raise TaxonomyCompatibilityError(
                f"Rubric type {rubric_key.value!r} is not compatible with "
                f"assessment type {assessment_key.value!r}."
            )
