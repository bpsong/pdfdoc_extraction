"""CLI help contract tests."""

import pytest

from tools.config_check.__main__ import create_parser


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (
            ["--help"],
            (
                "--all-stored",
                "validate-file --file pipeline.yaml --kind pipeline",
                "0 = Valid (no errors or warnings)",
            ),
        ),
        (
            ["validate", "--help"],
            (
                "--pipeline KEY",
                "--review-schema KEY",
                "--all-stored",
                "0 = Valid (no errors or warnings)",
            ),
        ),
        (
            ["validate-file", "--help"],
            ("--kind {runtime,pipeline,review-schema}", "--file FILE_OPTION"),
        ),
    ],
)
def test_help_documents_current_source_contracts(
    arguments: list[str],
    expected: tuple[str, ...],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Help output exposes implemented selectors and accurate exit semantics."""
    with pytest.raises(SystemExit) as exc_info:
        create_parser().parse_args(arguments)

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    for fragment in expected:
        assert fragment in output
