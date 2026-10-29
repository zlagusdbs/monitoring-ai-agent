import pytest

import skills


@pytest.fixture(autouse=True)
def here(tmp_path, monkeypatch):
    monkeypatch.setattr(skills, "DIR", tmp_path / "skills")


def test_round_trip():
    assert skills.write("skills", "runbook", "# 런북\n쿠폰부터 본다") is None
    assert skills.read("skills", "runbook").startswith("# 런북")
    assert skills.names("skills") == ["runbook"]


def test_groups_are_separate():
    skills.write("rules", "tone", "짧게 쓴다")
    skills.write("skills", "tone", "쿠폰부터")
    assert skills.read("rules", "tone") == "짧게 쓴다"
    assert skills.read("skills", "tone") == "쿠폰부터"
    assert skills.listing() == {"rules": ["tone"], "skills": ["tone"]}


@pytest.mark.parametrize("group", ["root", "../..", "", "Skills"])
def test_unknown_group_is_refused(group):
    assert skills.write(group, "x", "x") is not None
    assert skills.read(group, "x") is None
    assert skills.delete(group, "x") is False
    assert skills.names(group) == []


@pytest.mark.parametrize("name", ["../etc/passwd", "a/b", "A", "", "-x", "x" * 41, "a.b"])
def test_bad_names_are_refused(name):
    assert skills.write("skills", name, "x") is not None
    assert skills.read("skills", name) is None
    assert skills.delete("skills", name) is False


def test_path_traversal_cannot_escape(tmp_path):
    outside = tmp_path / "secret.md"
    outside.write_text("비밀", encoding="utf-8")
    assert skills.write("skills", "../../secret", "덮어쓰기") is not None
    assert outside.read_text(encoding="utf-8") == "비밀"


def test_too_big_is_refused():
    assert skills.write("skills", "big", "가" * 30000) is not None


def test_delete_removes_it():
    skills.write("skills", "gone", "x")
    assert skills.delete("skills", "gone") is True
    assert skills.names("skills") == []


def test_prompt_is_empty_without_files():
    assert skills.as_prompt() == ""


def test_prompt_carries_every_group():
    skills.write("rules", "one", "첫째")
    skills.write("skills", "two", "둘째")
    out = skills.as_prompt()
    assert "### one" in out and "첫째" in out
    assert "### two" in out and "둘째" in out
    assert out.index("첫째") < out.index("둘째")  # 규칙이 먼저 온다
    assert "도구와 권한은 바뀌지 않는다" in out


def test_blank_file_is_skipped():
    skills.write("skills", "empty", "   \n ")
    assert skills.as_prompt() == ""
