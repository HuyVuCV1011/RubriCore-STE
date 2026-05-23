# Test Fixtures

RubriCore-STE fixtures model assessment materials, answer-key sources, and learner submission evidence without exposing real learner data.

## Layout

```text
tests/fixtures/
├── public/              # Synthetic, sanitized, commit-safe fixtures
└── private/             # Local-only sensitive fixtures; ignored by Git

<fixture_set>/
├── assessment_materials/
├── answer_key_sources/
└── submission_evidence/
```

Fixture files are classified by workflow purpose, not by extension. A `.pdf`, `.py`, `.csv`, image, spreadsheet, archive, or text file can be assessment material, an answer-key source, submitted learner evidence, or a reference artifact depending on how it enters the assessment workflow.

## Public Fixtures

Public fixtures must be synthetic, sanitized, and safe to commit.

Use public fixtures for:

- repeatable unit tests
- documentation examples
- public demos
- CI-safe grading and artifact-provenance checks

Do not commit:

- real student work
- private answer keys
- private prompts
- credentials or API keys
- confidential teaching materials
- unpublished evaluation datasets
- sensitive school, learner, or teacher information

## Private Fixtures

Private fixtures are local-only materials for testing with sensitive or real-world examples.

Rules:

- keep them ignored by Git
- do not document personally identifying details in tracked files
- prefer a matching public fixture fallback for automated tests
- never require private fixtures for CI or clean-clone verification

## Test Strategy

Tests should prefer this pattern:

1. Use a private fixture only when it exists locally and the test is explicitly local/private.
2. Fall back to the matching public fixture for normal development and CI.
3. Assert artifact purpose and provenance explicitly.
4. Avoid deriving fixture role from file extension alone.

This keeps the public test suite useful while preserving the project’s data-safety boundary.
