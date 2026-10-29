from app.features.home.urls import HOME


async def test_home_lists_the_apps(client):
    r = await client.get(HOME.href())
    assert r.status_code == 200
    assert 'href="/a/alpha"' in r.text
    assert 'href="/a/beta"' in r.text
    assert "alpha.example" in r.text
