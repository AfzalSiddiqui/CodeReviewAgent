from app.github_comments import parse_diff_lines, parse_valid_lines

PATCH = "\n".join([
    "@@ -10,3 +10,4 @@ def handler():",
    " context_a",
    "-removed_line",
    "+added_one",
    "+added_two",
    " context_b",
])


def test_new_side_line_numbers_skip_deleted_lines():
    lines = parse_diff_lines(PATCH)
    assert [l["line"] for l in lines] == [10, 11, 12, 13]


def test_line_types_and_content():
    lines = parse_diff_lines(PATCH)
    assert [l["type"] for l in lines] == ["context", "added", "added", "context"]
    assert lines[1]["content"] == "added_one"
    assert lines[0]["content"] == "context_a"


def test_multiple_hunks_reset_line_numbers():
    patch = "@@ -1,1 +1,1 @@\n+first\n@@ -50,1 +60,2 @@\n context\n+second"
    assert [l["line"] for l in parse_diff_lines(patch)] == [1, 60, 61]


def test_hunk_header_without_count():
    assert parse_diff_lines("@@ -5 +7 @@\n+only")[0]["line"] == 7


def test_lines_before_first_hunk_are_ignored():
    patch = "diff --git a/x b/x\nindex 123..456\n@@ -1,1 +1,1 @@\n+x"
    assert [l["line"] for l in parse_diff_lines(patch)] == [1]


def test_valid_lines_match_parsed_lines():
    assert parse_valid_lines(PATCH) == {l["line"] for l in parse_diff_lines(PATCH)}
