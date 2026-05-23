# Python Score Summary Demo

Public-safe demo fixture set for testing a small rubric-based grading workflow.

The assignment asks learners to implement simple Python functions for working with quiz scores. The files are intentionally small and synthetic so they can be committed to GitHub and used in automated tests, rule checks, rubric experiments, and feedback prototypes.

## Files

- `assessment_materials/problem_statement.md`: beginner-level coding exercise.
- `answer_key_sources/model_answer.py`: one valid reference implementation.
- `rubrics/scoring_guide.md`: simple scoring guide with criteria and point values.
- `knowledge_sources/teacher_grading_notes.md`: synthetic teacher guidance for review and feedback behavior.
- `knowledge_sources/common_misconceptions.md`: synthetic misconception notes for retrieval and chunking tests.
- `knowledge_sources/rubric_suggestion_seed.md`: synthetic seed material for teacher-approved rubric suggestions.
- `knowledge_sources/conversion_source.txt`: simple plain-text source for conversion tests.
- `submission_evidence/student_001_correct.py`: correct direct solution.
- `submission_evidence/student_002_partial.py`: partially correct, misses one requirement.
- `submission_evidence/student_003_incorrect.py`: incorrect logic and missing edge-case handling.
- `submission_evidence/student_004_alternative_valid.py`: correct alternative implementation.
- `submission_evidence/student_005_syntax_error.py`: invalid Python syntax for parser/error handling tests.
- `manifest.json`: machine-readable index for fixture loading.

All content is fictional, synthetic, and public-safe.
