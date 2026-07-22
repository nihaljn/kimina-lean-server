from server.split import split_snippet


def test_only_imports() -> None:
    code = "import A\nimport Mathlib\nimport B"
    result = split_snippet(code)
    assert result.header.splitlines() == ["import Mathlib", "import A", "import B"]
    assert result.body == ""
    assert result.header_line_count == 3


def test_imports_and_body() -> None:
    code = "import X\n\nimport Mathlib\nimport Y\n\ndef foo():\n    pass"
    result = split_snippet(code)
    assert result.header.splitlines() == ["import Mathlib", "import X", "import Y"]
    assert result.body.splitlines() == ["def foo():", "    pass"]
    assert result.header_line_count == 5


def test_no_imports() -> None:
    code = "def bar():\n    return 1"
    result = split_snippet(code)
    assert result.header == ""
    assert result.body == code
    assert result.header_line_count == 0


def test_duplicate_imports() -> None:
    code = "import Mathlib\nimport Mathlib\nimport Z\nimport Z\nZ"
    result = split_snippet(code)
    assert result.header.splitlines() == ["import Mathlib", "import Z"]
    assert result.body.splitlines() == ["Z"]
    assert result.header_line_count == 4


def test_single_mathlib_import() -> None:
    code = "import Mathlib"
    result = split_snippet(code)
    assert result.header == code
    assert result.body == ""
    assert result.header_line_count == 1


def test_single_mathlib_import_with_trailing_spaces() -> None:
    code = """import Mathlib  

theorem one_plus_one : 1 + 1 = 2 := by rfl"""

    result = split_snippet(code)
    assert result.header == "import Mathlib"
    assert result.body == "theorem one_plus_one : 1 + 1 = 2 := by rfl"
    assert result.header_line_count == 2


def test_multiple_imports() -> None:
    code = """import Mathlib
import Aesop

theorem one_plus_one : 1 + 1 = 2 := by
  sorry"""

    result = split_snippet(code)
    assert result.header == "import Mathlib\nimport Aesop"
    assert (
        result.body
        == """theorem one_plus_one : 1 + 1 = 2 := by
  sorry"""
    )
    assert result.header_line_count == 3


def test_multiple_imports_preceded_by_eols() -> None:
    code = """

import Mathlib
import Aesop
theorem one_plus_one : 1 + 1 = 2 := by
  sorry"""

    result = split_snippet(code)
    assert result.header == "import Mathlib\nimport Aesop"
    assert (
        result.body
        == """theorem one_plus_one : 1 + 1 = 2 := by
  sorry"""
    )
    assert result.header_line_count == 4


def test_multiple_separated_imports() -> None:
    code = """import Mathlib

import Aesop

theorem one_plus_one : 1 + 1 = 2 := by
  sorry"""

    result = split_snippet(code)
    assert result.header == "import Mathlib\nimport Aesop"
    assert (
        result.body
        == """theorem one_plus_one : 1 + 1 = 2 := by
  sorry"""
    )
    assert result.header_line_count == 4


def test_multiple_mathlib_imports() -> None:
    code = """import Mathlib.Tactic
import Aesop
import Mathlib.Data.Nat"""
    result = split_snippet(code)
    assert result.header == "import Mathlib\nimport Aesop"
    assert result.body == ""
    assert result.header_line_count == 3


def test_lean_options_are_appended_to_the_header(monkeypatch) -> None:
    from server.settings import settings

    monkeypatch.setattr(settings, "lean_options", {"autoImplicit": "false"})
    code = "import Mathlib\n\nopen Real\n\ndef foo := 1"
    result = split_snippet(code)
    assert result.header.splitlines() == [
        "import Mathlib",
        "set_option autoImplicit false",
    ]
    # the option is added to the REBUILT header, so the body offset is unchanged
    assert result.header_line_count == 2
    assert result.body.splitlines() == ["open Real", "", "def foo := 1"]


def test_no_lean_options_leaves_the_header_alone(monkeypatch) -> None:
    from server.settings import settings

    monkeypatch.setattr(settings, "lean_options", {})
    result = split_snippet("import Mathlib\n\ndef foo := 1")
    assert result.header.splitlines() == ["import Mathlib"]
