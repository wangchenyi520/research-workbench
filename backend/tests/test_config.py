from app import config


def test_paths_are_local():
    assert config.DATA_DIR.name == "data"
    assert config.DB_PATH.name == "workbench.db"
    assert config.DATABASE_URL.startswith("sqlite:///")
    assert config.DAILY_PAPER_DIR.name == "daily_paper"
