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


def test_packs_endpoint(client):
    r = upload(client, seed=40, context_tags="Comedy Pack")
    upload(client, seed=41, context_tags="Comedy Pack")
    wait_done(client, r.json()["meme"]["id"])
    packs = client.get("/api/packs").json()["packs"]
    assert packs and packs[0]["name"] == "Comedy Pack" and packs[0]["count"] == 2
    assert packs[0]["cover_url"].startswith("/images/")
    listed = client.get("/api/memes?pack=Comedy%20Pack").json()
    assert listed["total"] == 2


def test_auto_tag_merges_actors(client):
    r = upload(client, seed=50, actors="Chiranjeevi")
    meme_id = r.json()["meme"]["id"]
    wait_done(client, meme_id)
    out = client.post(
        f"/api/memes/{meme_id}/auto_tag", json={"actors": ["Brahmanandam"]}
    ).json()["meme"]
    assert out["actors"] == ["Brahmanandam", "Chiranjeevi"]  # merged, not replaced
    assert not out["verified"]  # auto-tagging never marks verified
    # No-op merge enqueues nothing new and keeps tags stable.
    out2 = client.post(
        f"/api/memes/{meme_id}/auto_tag", json={"actors": ["Chiranjeevi"]}
    ).json()["meme"]
    assert out2["actors"] == ["Brahmanandam", "Chiranjeevi"]


def test_bulk_delete(client):
    import config

    ids = []
    for seed in range(60, 63):
        r = upload(client, seed=seed, context_tags="Junk Pack")
        ids.append(r.json()["meme"]["id"])
    for mid in ids:
        wait_done(client, mid)
    image_paths = [
        config.IMAGES_DIR / client.get(f"/api/memes/{m}").json()["meme"]["image_path"]
        for m in ids
    ]
    assert all(p.exists() for p in image_paths)

    res = client.post("/api/memes/bulk_delete", json={"ids": ids + ["nonexistent"]})
    assert res.json()["deleted"] == 3
    assert client.get(f"/api/memes/{ids[0]}").status_code == 404
    assert not any(p.exists() for p in image_paths)  # image files removed
    # Gone from keyword search and from the vector index.
    assert client.post("/api/memes/search", json={"query": "జీవితం"}).json()["results"] == []
    assert client.get("/api/memes?pack=Junk%20Pack").json()["total"] == 0


def test_admin_page_served(client):
    r = client.get("/admin")
    assert r.status_code == 200 and "Admin" in r.text


def test_face_cluster_labeling(client):
    import numpy as np
    from db import store as st

    r = upload(client, seed=70)
    m1 = r.json()["meme"]["id"]
    m2 = upload(client, seed=71).json()["meme"]["id"]
    wait_done(client, m1); wait_done(client, m2)

    conn = client.app.state.conn
    emb = np.random.rand(512).astype(np.float32).tobytes()
    for mid in (m1, m2):
        fid = st.insert_face(conn, mid, [0, 0, 10, 10], emb)
        st.set_face_clusters(conn, {fid: 1})

    clusters = client.get("/api/faces/clusters?min_count=2").json()["clusters"]
    assert clusters and clusters[0]["cluster"] == 1 and clusters[0]["memes"] == 2
    assert clusters[0]["label"] is None

    res = client.post("/api/faces/clusters/1/label", json={"name": "Sunil"}).json()
    assert res["memes"] == 2 and res["newly_tagged"] == 2
    assert "Sunil" in client.get(f"/api/memes/{m1}").json()["meme"]["actors"]
    # Cluster filter on the list endpoint.
    assert client.get("/api/memes?cluster=1").json()["total"] == 2
    # Label persisted; unlabeled_only hides it now.
    assert client.get("/api/faces/clusters?unlabeled_only=true").json()["clusters"] == []
    assert client.post("/api/faces/clusters/99/label", json={"name": "X"}).status_code == 404


def test_cluster_describe_and_delete(client):
    import numpy as np
    import config
    from db import store as st

    m1 = upload(client, seed=80).json()["meme"]["id"]
    m2 = upload(client, seed=81).json()["meme"]["id"]
    wait_done(client, m1); wait_done(client, m2)
    conn = client.app.state.conn
    emb = np.random.rand(512).astype(np.float32).tobytes()
    for mid in (m1, m2):
        fid = st.insert_face(conn, mid, [0, 0, 10, 10], emb)
        st.set_face_clusters(conn, {fid: 5})
    client.post("/api/faces/clusters/5/label", json={"name": "Kota"})

    # Describe: fills the description field, searchable, idempotent on re-describe.
    r = client.post(
        "/api/faces/clusters/5/describe",
        json={"description": "grumpy uncle villain sarcastic"},
    ).json()
    assert r["memes"] == 2
    desc = client.get(f"/api/memes/{m1}").json()["meme"]["description"]
    assert "[face #5] Kota: grumpy uncle villain sarcastic" in desc
    hits = client.post("/api/memes/search", json={"query": "grumpy uncle"}).json()
    assert {x["meme"]["id"] for x in hits["results"]} >= {m1, m2}
    client.post("/api/faces/clusters/5/describe", json={"description": "updated text"})
    desc = client.get(f"/api/memes/{m1}").json()["meme"]["description"]
    assert desc.count("[face #5]") == 1 and "updated text" in desc
    clusters = client.get("/api/faces/clusters?min_count=2").json()["clusters"]
    assert clusters[0]["description"] == "updated text"

    # Delete whole cluster: memes, images, crops all gone.
    img = config.IMAGES_DIR / client.get(f"/api/memes/{m1}").json()["meme"]["image_path"]
    res = client.delete("/api/faces/clusters/5").json()
    assert res["deleted"] == 2
    assert client.get(f"/api/memes/{m1}").status_code == 404
    assert not img.exists()
    assert client.delete("/api/faces/clusters/5").status_code == 404


def test_description_outranks_caption(client):
    """A curated description should beat an auto-caption for the same query."""
    # m_desc: description mentions the concept; caption is the generic fake.
    m_desc = upload(client, seed=90, description="man dancing at a wedding party").json()["meme"]["id"]
    m_plain = upload(client, seed=91).json()["meme"]["id"]
    wait_done(client, m_desc); wait_done(client, m_plain)

    r = client.post(
        "/api/memes/search", json={"query": "dancing at a wedding party", "limit": 5}
    ).json()
    ids = [x["meme"]["id"] for x in r["results"]]
    assert ids[0] == m_desc
    assert "description" in r["results"][0]["reasons"]["matched_fields"]


def test_edit_description_reembeds(client):
    m = upload(client, seed=92).json()["meme"]["id"]
    wait_done(client, m)
    client.post(f"/api/memes/{m}/edit", json={"description": "elephant riding a bicycle"})
    wait_done(client, m)
    r = client.post("/api/memes/search", json={"query": "elephant bicycle"}).json()
    assert r["results"] and r["results"][0]["meme"]["id"] == m
