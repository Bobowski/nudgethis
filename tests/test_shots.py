async def test_shot_names_are_validated(client):
    assert (await client.get("/shots/../secret")).status_code == 404
    assert (await client.get("/shots/..%2F..%2Fenv")).status_code == 404
    assert (await client.get("/shots/ABCD.png")).status_code == 404
    assert (await client.get("/shots/notashot.txt")).status_code == 404
    assert (await client.get("/shots/a1b2c3d4.png")).status_code == 404
