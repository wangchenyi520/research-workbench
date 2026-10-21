from app.services.self_analysis import scan


def test_scan_finds_markdown_and_skips_hidden_dirs(tmp_path):
    (tmp_path / "plan").mkdir()
    (tmp_path / "plan" / "b.md").write_text("b", encoding="utf-8")
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "x.md").write_text("x", encoding="utf-8")
    (tmp_path / ".vscode").mkdir()
    (tmp_path / ".vscode" / "y.md").write_text("y", encoding="utf-8")

    files = scan(tmp_path)
    assert [path.name for path in files] == ["a.md", "b.md"]


def test_scan_missing_folder_returns_empty(tmp_path):
    assert scan(tmp_path / "missing") == []
