import pytest

from tests.factories import add_member, login, make_org, make_user


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture(autouse=True)
def _clear_cache():
    """Rate-limit counters live in the cache; every test starts fresh."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def org1(db):
    return make_org("Savannah Test Safaris", pack="tourism", sub_niche="tour_operator", slug="savannah-test")


@pytest.fixture
def org2(db):
    return make_org("ORG2SECRET Homes", pack="real_estate", sub_niche="agency", slug="org2-homes")


@pytest.fixture
def owner1(org1):
    return org1.memberships.get(role__key="owner").user


@pytest.fixture
def owner2(org2):
    return org2.memberships.get(role__key="owner").user


@pytest.fixture
def client1(client, owner1):
    return login(client, owner1)


@pytest.fixture
def staff1(org1):
    return add_member(org1, make_user(full_name="Staff One"), role="staff")


@pytest.fixture
def make_member():
    return add_member


@pytest.fixture
def user_factory(db):
    return make_user
