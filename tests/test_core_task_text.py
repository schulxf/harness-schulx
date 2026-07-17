from __future__ import annotations

from harness_core.task_text import extract_checklist, extract_out_of_scope, slugify


def test_slugify_basic_and_edge_cases() -> None:
    assert slugify("Hello World") == "hello-world"
    assert slugify("  Foo!!! Bar  --  Baz  ") == "foo-bar-baz"
    assert slugify("!!!") == "untitled"
    assert slugify("x" * 200) == "x" * 80


def test_extract_checklist_picks_up_acceptance_items() -> None:
    text = (
        "# Task\n\n"
        "## Criterios de aceite\n\n"
        "- [ ] Save user\n"
        "- [x] Load user\n"
        "- [ ] TODO: define later\n"
        "\n## Fora de escopo\n\n- Billing\n"
    )

    assert extract_checklist(text) == ["Save user", "Load user"]


def test_extract_checklist_returns_empty_when_no_section() -> None:
    assert extract_checklist("# Task\n\nNo sections here.\n") == []


def test_extract_out_of_scope_supports_portuguese_and_english_headings() -> None:
    assert extract_out_of_scope("## Fora de escopo\n- OAuth\n- TODO: define\n- Billing\n") == [
        "OAuth",
        "Billing",
    ]
    assert extract_out_of_scope("## Out of scope\n- Telemetry\n") == ["Telemetry"]
