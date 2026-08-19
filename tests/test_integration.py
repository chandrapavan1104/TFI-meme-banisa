"""End-to-end API flow with real embedded Qdrant and fake ML collectors:
upload -> jobs -> search (vector + keyword) -> edit -> re-search.
"""

from tests.conftest import make_image_bytes, upload, wait_done


def test_health(client):
    h = client.get("/health").json()
    assert h["qdrant"]["collection_ready"]


def test_upload_validation(client):
    r = client.post(
        "/api/memes/upload",
        files={"file": ("x.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 415
    r = client.post(
        "/api/memes/upload",
        files={"file": ("x.png", b"not-a-real-png", "image/png")},
    )
    assert r.status_code == 422


def test_full_workflow(client):
    # 1. Upload with partial metadata.
    r = upload(
        client, seed=1,
        movie_title_en="Indra", actors="Chiranjeevi", emotion_tags="sad,anger",
    )
    assert r.status_code == 201
    meme = r.json()["meme"]
    meme_id = meme["id"]
    assert meme["image_url"].startswith("/images/")

    # 2. Jobs run: caption + OCR + embed (fakes).
    status = wait_done(client, meme_id)
    assert status["progress"] == 100 and status["errors"] == []

    detail = client.get(f"/api/memes/{meme_id}").json()["meme"]
    assert detail["caption"] == "a man crying in the rain"
    assert "జీవితం" in detail["dialogue_te"]  # OCR text promoted to dialogue

    # 3. Vector search finds it semantically.
    r = client.post("/api/memes/search", json={"query": "man crying rain"}).json()
    assert r["results"] and r["results"][0]["meme"]["id"] == meme_id
    assert r["results"][0]["reasons"]["vector_score"] is not None

    # 4. Keyword (BM25) search on exact dialogue.
    r = client.post("/api/memes/search", json={"query": "జీవితం"}).json()
    assert r["results"] and r["results"][0]["meme"]["id"] == meme_id
    assert r["results"][0]["reasons"]["keyword_rank"] == 1

    # 5. Roman-script query gets transliterated.
    r = client.post("/api/memes/search", json={"query": "jIvitaM"}).json()
    assert "query_telugu" in r

    # 6. Filters.
    r = client.post(
        "/api/memes/search", json={"query": "crying", "emotions": ["sad"]}
    ).json()
    assert r["results"][0]["meme"]["id"] == meme_id
    r = client.post(
        "/api/memes/search", json={"query": "crying", "emotions": ["happy"]}
    ).json()
    assert r["results"] == []

    # 7. Edit marks verified, persists, and re-embeds.
    r = client.post(
        f"/api/memes/{meme_id}/edit",
        json={"dialogue_en": "this life is a battle", "context_tags": ["intro scene"]},
    ).json()
    assert r["meme"]["verified"] and r["meme"]["dialogue_en"] == "this life is a battle"
    wait_done(client, meme_id)
    r = client.post("/api/memes/search", json={"query": "battle"}).json()
    assert r["results"][0]["meme"]["id"] == meme_id
    assert r["results"][0]["reasons"]["verified"]

    # 8. Lookup endpoints.
    assert client.get("/api/actors").json()["actors"] == ["Chiranjeevi"]
    assert "sad" in client.get("/api/emotions").json()["emotions"]
    movies = client.get("/api/movies").json()["movies"]
    assert movies[0]["movie_title_en"] == "Indra"

    # 9. Analytics recorded the searches.
    top = client.get("/api/analytics/top_queries").json()["queries"]
    assert any(q["query"] == "crying" for q in top)


def test_duplicate_upload_reprocesses(client):
    r1 = upload(client, seed=2)
    assert r1.status_code == 201
    meme_id = r1.json()["meme"]["id"]
    wait_done(client, meme_id)

    r2 = upload(client, seed=2)
    assert r2.status_code == 200 and r2.json()["duplicate"]
    # New jobs were enqueued (6 total: two pipelines).
    wait_done(client, meme_id)
    status = client.get(f"/api/memes/{meme_id}/status").json()
    assert len(status["jobs"]) == 6


def test_pagination_and_rating(client):
    ids = []
    for seed in range(3):
        r = upload(client, seed=10 + seed)
        ids.append(r.json()["meme"]["id"])
    for mid in ids:
        wait_done(client, mid)

    page = client.get("/api/memes?limit=2&offset=0").json()
    assert page["total"] == 3 and len(page["memes"]) == 2
    page2 = client.get("/api/memes?limit=2&offset=2").json()
    assert len(page2["memes"]) == 1

    r = client.post(f"/api/memes/{ids[0]}/rate", json={"rating": 5})
    assert r.json()["meme"]["rating"] == 5
    assert client.post(f"/api/memes/{ids[0]}/rate", json={"rating": 9}).status_code == 422

    verified = client.get("/api/memes?verified=true").json()
    assert verified["total"] == 0


def test_empty_query(client):
    r = client.post("/api/memes/search", json={"query": "   "}).json()
    assert r["results"] == []


def test_404s(client):
    assert client.get("/api/memes/doesnotexist").status_code == 404
    assert client.get("/api/memes/doesnotexist/status").status_code == 404
    assert (
        client.post("/api/memes/doesnotexist/edit", json={}).status_code == 404
    )


def test_upload_size_limit(client, monkeypatch):
    import config

    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 0)
    data = make_image_bytes(seed=99)
    r = client.post(
        "/api/memes/upload", files={"file": ("big.png", data, "image/png")}
    )
    assert r.status_code == 413
