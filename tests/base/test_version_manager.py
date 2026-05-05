from base.Base import Base
from base.VersionManager import VersionManager


def test_release_urls_point_to_fork_repository() -> None:
    assert Base.REPO_URL == "https://github.com/xccxcxxc/LinguaGacha"
    assert (
        VersionManager.get_release_url()
        == "https://github.com/xccxcxxc/LinguaGacha/releases/latest"
    )
    assert (
        VersionManager.get_release_api_url()
        == "https://api.github.com/repos/xccxcxxc/LinguaGacha/releases/latest"
    )
