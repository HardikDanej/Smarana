import math

from memory_os.embedding import HashingEmbedder, cosine_similarity


def test_embedding_is_deterministic():
    embedder = HashingEmbedder()
    assert embedder.embed("Project Alpha uses PostgreSQL") == embedder.embed(
        "Project Alpha uses PostgreSQL"
    )


def test_embedding_is_l2_normalized():
    embedder = HashingEmbedder()
    vector = embedder.embed("Project Alpha uses PostgreSQL and runs on GCP")
    norm = math.sqrt(sum(v * v for v in vector))
    assert norm == 0.0 or abs(norm - 1.0) < 1e-9


def test_shared_vocabulary_yields_positive_similarity():
    embedder = HashingEmbedder()
    a = embedder.embed("Project Alpha uses PostgreSQL")
    b = embedder.embed("Project Alpha migrated its PostgreSQL database")
    assert cosine_similarity(a, b) > 0


def test_disjoint_vocabulary_yields_zero_similarity():
    embedder = HashingEmbedder(dimensions=4096)  # large space, low collision odds
    a = embedder.embed("zebra xylophone")
    b = embedder.embed("quantum turbine")
    assert cosine_similarity(a, b) == 0.0


def test_identical_text_has_similarity_of_one():
    embedder = HashingEmbedder()
    vector = embedder.embed("Project Alpha uses PostgreSQL")
    assert abs(cosine_similarity(vector, vector) - 1.0) < 1e-9
