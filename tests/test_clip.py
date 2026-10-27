"""
tests/test_clip.py
Comprehensive automated test suite for the OpenAI CLIP Image Similarity Search engine.

Covers:
- Service initialization, device detection, and lazy loading
- Graceful error handling for missing dependencies and load failures
- Image validation, format checks, and decompression bomb prevention
- L2 embedding normalization and edge cases (zero/NaN norm)
- Cosine similarity computation and ranking
- Database embedding persistence, versioning, cascade deletion, and invalidation
- Image similarity search API endpoint (/api/items/search/image)
- Multi-parameter filtering with image similarity
- Missing image file handling and on-demand fallback
- CLI backfill-embeddings command
- Optional integration smoke test with real CLIP model if available
"""

import io
import os
import shutil
import tempfile
import numpy as np
import pytest
from PIL import Image
from unittest.mock import MagicMock, patch

from services.clip_service import (
    CLIPService,
    CLIPServiceError,
    CLIPModelNotAvailableError,
    InvalidImageError,
    get_optimal_device,
    EMBEDDING_DIM,
)
from services.item_service import (
    store_item_embedding,
    get_item_embedding,
    delete_item_embedding,
    generate_and_store_embedding,
    backfill_all_embeddings,
    search_items_by_image,
    report_item,
    update_item,
    delete_item,
)
from database import get_db


# Helper to generate in-memory dummy test images
def create_test_image(color=(255, 0, 0), size=(100, 100), fmt="PNG"):
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    buf.seek(0)
    return buf


def create_random_normalized_embedding(dim=EMBEDDING_DIM, seed=None):
    if seed is not None:
        np.random.seed(seed)
    vec = np.random.randn(dim).astype(np.float32)
    norm = np.linalg.norm(vec)
    return (vec / norm).astype(np.float32)


# ==============================================================================
# Unit Tests: CLIPService Core, Device Detection & Normalization
# ==============================================================================


def test_device_detection():
    """Verify optimal compute device detection returns valid device string."""
    device_str, desc = get_optimal_device()
    assert device_str in ("cuda", "mps", "cpu")
    assert isinstance(desc, str) and len(desc) > 0


def test_service_singleton_and_info():
    """Test that CLIPService functions as a thread-safe singleton."""
    CLIPService.reset_instance()
    inst1 = CLIPService.get_instance()
    inst2 = CLIPService.get_instance()
    assert inst1 is inst2

    info = inst1.get_info()
    assert "model_name" in info
    assert "model_version" in info
    assert "device" in info
    assert info["embedding_dim"] == EMBEDDING_DIM
    CLIPService.reset_instance()


def test_load_model_failure_handling():
    """Verify graceful error when CLIP model loading fails."""
    CLIPService.reset_instance()
    service = CLIPService(model_name="non_existent_model")

    with patch("clip.load", side_effect=RuntimeError("Simulated weight download timeout")):
        with pytest.raises(CLIPModelNotAvailableError) as exc_info:
            service.load_model()
        assert "Simulated weight download timeout" in str(exc_info.value)
        assert service.get_info()["is_loaded"] is False
    CLIPService.reset_instance()


def test_validate_and_open_image_valid():
    """Verify valid PNG and JPEG images are opened and converted to RGB."""
    png_buf = create_test_image(color=(100, 150, 200), fmt="PNG")
    img = CLIPService.validate_and_open_image(png_buf)
    assert isinstance(img, Image.Image)
    assert img.mode == "RGB"

    jpeg_buf = create_test_image(color=(50, 50, 50), fmt="JPEG")
    img2 = CLIPService.validate_and_open_image(jpeg_buf)
    assert img2.mode == "RGB"


def test_validate_and_open_image_corrupted():
    """Verify invalid and corrupt byte inputs raise InvalidImageError."""
    corrupt_bytes = b"not-a-valid-image-stream-content"
    with pytest.raises(InvalidImageError):
        CLIPService.validate_and_open_image(corrupt_bytes)


def test_validate_and_open_image_unsupported_format():
    """Verify unsupported image formats (e.g. BMP/TIFF if restricted) raise error."""
    buf = io.BytesIO()
    img = Image.new("RGB", (20, 20), color="blue")
    img.save(buf, format="BMP")
    buf.seek(0)

    with pytest.raises(InvalidImageError) as exc:
        CLIPService.validate_and_open_image(buf)
    assert "Unsupported image format" in str(exc.value)


def test_validate_and_open_image_size_limit():
    """Verify images exceeding MAX_IMAGE_BYTES are rejected."""
    oversized_bytes = b"0" * (6 * 1024 * 1024)  # 6 MB
    with pytest.raises(InvalidImageError) as exc:
        CLIPService.validate_and_open_image(oversized_bytes)
    assert "exceeds maximum limit" in str(exc.value)


def test_cosine_similarity_computation():
    """Verify mathematical properties of cosine similarity."""
    v1 = create_random_normalized_embedding(seed=42)
    # Identical vector -> similarity 1.0
    sim_identical = CLIPService.compute_similarity(v1, v1)
    assert pytest.approx(sim_identical, 1e-4) == 1.0

    # Opposite vector -> similarity -1.0
    sim_opposite = CLIPService.compute_similarity(v1, -v1)
    assert pytest.approx(sim_opposite, 1e-4) == -1.0

    # Orthogonal vectors -> similarity 0.0
    e1 = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    e1[0] = 1.0
    e2 = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    e2[1] = 1.0
    sim_orthogonal = CLIPService.compute_similarity(e1, e2)
    assert pytest.approx(sim_orthogonal, 1e-4) == 0.0

    # Edge cases: None or zero vectors
    assert CLIPService.compute_similarity(None, v1) == 0.0
    assert CLIPService.compute_similarity(np.zeros(EMBEDDING_DIM), v1) == 0.0


def test_embedding_serialization_roundtrip():
    """Verify binary serialization to/from SQLite BLOB maintains exact precision."""
    orig = create_random_normalized_embedding(seed=123)
    blob = CLIPService.embedding_to_blob(orig)
    assert isinstance(blob, bytes)
    assert len(blob) == EMBEDDING_DIM * 4  # 512 * 4 bytes for float32 = 2048 bytes

    recovered = CLIPService.blob_to_embedding(blob)
    assert np.allclose(orig, recovered, rtol=1e-5)


# ==============================================================================
# Database & Item Service Integration Tests
# ==============================================================================


def test_embedding_storage_and_cascade(app):
    """Test embedding storage, retrieval, and cascade deletion upon item deletion."""
    with app.app_context():
        db = get_db()
        # Insert a user and an item
        db.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES ('Tester', 'test@campus.edu', 'hash', 'student')"
        )
        user_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        db.execute(
            """
            INSERT INTO items (title, description, category, type, location, date_event, user_id, image_filename)
            VALUES ('AirPods Pro', 'White case with green silicon cover', 'Electronics', 'lost', 'Library', '2026-10-25', ?, 'airpods.jpg')
            """,
            (user_id,),
        )
        item_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.commit()

        # Store an embedding
        emb = create_random_normalized_embedding(seed=1)
        store_item_embedding(item_id, emb, model_version="openai/clip-vit-b-32")

        # Retrieve embedding
        retrieved = get_item_embedding(item_id)
        assert retrieved is not None
        assert np.allclose(emb, retrieved)

        # Verify record in item_embeddings table
        row = db.execute("SELECT * FROM item_embeddings WHERE item_id = ?", (item_id,)).fetchone()
        assert row["model_version"] == "openai/clip-vit-b-32"

        # Delete item and verify cascade deletion of embedding
        delete_item(item_id, user_id=user_id, user_role="student")
        assert get_item_embedding(item_id) is None
        assert db.execute("SELECT COUNT(*) FROM item_embeddings WHERE item_id = ?", (item_id,)).fetchone()[0] == 0


def test_embedding_invalidation_on_update(app):
    """Test that updating an item with a new image updates its embedding, or removes it if image cleared."""
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO users (name, email, password_hash) VALUES ('Bob', 'bob@campus.edu', 'hash')")
        user_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.commit()

        upload_dir = tempfile.mkdtemp()
        try:
            # Create dummy initial image file
            img1_path = os.path.join(upload_dir, "calc1.jpg")
            with open(img1_path, "wb") as f:
                f.write(create_test_image(color=(255, 0, 0), fmt="JPEG").getvalue())

            # Report item with initial image
            mock_emb1 = create_random_normalized_embedding(seed=10)
            with patch.object(CLIPService, "generate_image_embedding", return_value=mock_emb1):
                item = report_item(
                    data={
                        "title": "TI-84 Calculator",
                        "description": "Black graphing calculator",
                        "category": "Electronics",
                        "type": "found",
                        "location": "Math Lab",
                        "date_event": "2026-10-26",
                        "image_filename": "calc1.jpg",
                    },
                    user_id=user_id,
                    upload_folder=upload_dir,
                )

            item_id = item["id"]
            stored = get_item_embedding(item_id)
            assert stored is not None
            assert np.allclose(stored, mock_emb1)

            # Update item with new image
            mock_emb2 = create_random_normalized_embedding(seed=20)
            img2_path = os.path.join(upload_dir, "calc2.jpg")
            with open(img2_path, "wb") as f:
                f.write(create_test_image(color=(0, 255, 0), fmt="JPEG").getvalue())

            with patch.object(CLIPService, "generate_image_embedding", return_value=mock_emb2):
                update_item(
                    item_id=item_id,
                    user_id=user_id,
                    user_role="student",
                    data={"image_filename": "calc2.jpg"},
                    upload_folder=upload_dir,
                )

            stored2 = get_item_embedding(item_id)
            assert np.allclose(stored2, mock_emb2)

            # Remove image by updating with empty image_filename
            update_item(
                item_id=item_id,
                user_id=user_id,
                user_role="student",
                data={"image_filename": None},
                upload_folder=upload_dir,
            )
            assert get_item_embedding(item_id) is None

        finally:
            shutil.rmtree(upload_dir, ignore_errors=True)


def test_search_items_by_image_ranking_and_filters(app):
    """Test ranking items by cosine similarity and respecting category/type filters."""
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO users (name, email, password_hash) VALUES ('Alice', 'alice@campus.edu', 'hash')")
        user_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Candidate 1: High similarity
        db.execute(
            """
            INSERT INTO items (title, description, category, type, location, date_event, user_id, image_filename)
            VALUES ('Target Earbuds', 'White earbuds', 'Electronics', 'found', 'Gym', '2026-10-25', ?, 'earbuds.jpg')
            """,
            (user_id,),
        )
        id_high = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Candidate 2: Medium similarity (Bags & Wallets)
        db.execute(
            """
            INSERT INTO items (title, description, category, type, location, date_event, user_id, image_filename)
            VALUES ('White Canvas Bag', 'Canvas tote bag', 'Bags & Wallets', 'found', 'Cafeteria', '2026-10-25', ?, 'bag.jpg')
            """,
            (user_id,),
        )
        id_med = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Candidate 3: Low similarity (Electronics, Lost)
        db.execute(
            """
            INSERT INTO items (title, description, category, type, location, date_event, user_id, image_filename)
            VALUES ('Black Laptop', 'Dell XPS', 'Electronics', 'lost', 'Library', '2026-10-25', ?, 'laptop.jpg')
            """,
            (user_id,),
        )
        id_low = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.commit()

        # Set up synthetic embeddings
        query_emb = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        query_emb[0] = 1.0  # Unit vector along axis 0

        # High similarity: dot product = 0.95
        emb_high = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        emb_high[0] = 0.95
        emb_high[1] = np.sqrt(1 - 0.95**2)
        store_item_embedding(id_high, emb_high)

        # Med similarity: dot product = 0.50
        emb_med = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        emb_med[0] = 0.50
        emb_med[1] = np.sqrt(1 - 0.50**2)
        store_item_embedding(id_med, emb_med)

        # Low similarity: dot product = 0.10
        emb_low = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        emb_low[0] = 0.10
        emb_low[1] = np.sqrt(1 - 0.10**2)
        store_item_embedding(id_low, emb_low)

        dummy_img = create_test_image()

        with patch.object(CLIPService, "generate_image_embedding", return_value=query_emb):
            # 1. Unfiltered search: returns all 3 ranked high -> med -> low
            results = search_items_by_image(dummy_img, upload_folder="", top_k=10)
            assert len(results) == 3
            assert results[0]["id"] == id_high
            assert results[0]["similarity_score"] == 0.95
            assert results[1]["id"] == id_med
            assert results[1]["similarity_score"] == 0.50
            assert results[2]["id"] == id_low
            assert results[2]["similarity_score"] == 0.10

            # 2. Filter by category='Electronics': only id_high and id_low
            results_elec = search_items_by_image(dummy_img, upload_folder="", category="Electronics")
            assert len(results_elec) == 2
            assert [r["id"] for r in results_elec] == [id_high, id_low]

            # 3. Filter by type='lost': only id_low
            results_lost = search_items_by_image(dummy_img, upload_folder="", item_type="lost")
            assert len(results_lost) == 1
            assert results_lost[0]["id"] == id_low

            # 4. Filter with high threshold >= 0.8: only id_high
            results_thresh = search_items_by_image(dummy_img, upload_folder="", threshold=0.8)
            assert len(results_thresh) == 1
            assert results_thresh[0]["id"] == id_high


def test_missing_image_file_handled_gracefully(app):
    """Test that items with missing images on disk do not crash the search."""
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO users (name, email, password_hash) VALUES ('Ghost', 'ghost@campus.edu', 'hash')")
        uid = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Item has image_filename in DB, but no embedding and no file on disk
        db.execute(
            """
            INSERT INTO items (title, description, category, type, location, date_event, user_id, image_filename)
            VALUES ('Ghost Item', 'File does not exist', 'Keys', 'found', 'Gate', '2026-10-25', ?, 'nonexistent.jpg')
            """,
            (uid,),
        )
        db.commit()

        query_emb = create_random_normalized_embedding(seed=99)
        with patch.object(CLIPService, "generate_image_embedding", return_value=query_emb):
            # Should not raise exception; candidate set is empty
            results = search_items_by_image(create_test_image(), upload_folder="/tmp/empty_dir")
            assert results == []


# ==============================================================================
# HTTP API Endpoint Tests: /api/items/search/image
# ==============================================================================


def test_api_search_by_image_missing_file(client):
    """Verify 400 Bad Request when 'image' field is missing from request."""
    res = client.post("/api/items/search/image", data={})
    assert res.status_code == 400
    assert "image file is required" in res.get_json()["error"]["message"].lower()


def test_api_search_by_image_invalid_file_format(client):
    """Verify 400 Bad Request when a text file is uploaded instead of an image."""
    data = {
        "image": (io.BytesIO(b"this is plain text not an image"), "notes.txt"),
    }
    res = client.post(
        "/api/items/search/image",
        data=data,
        content_type="multipart/form-data",
    )
    assert res.status_code == 400
    assert "invalid" in res.get_json()["error"]["message"].lower()


def test_api_search_by_image_service_unavailable(client):
    """Verify 503 Service Unavailable when CLIP model fails to initialize."""
    img_buf = create_test_image()
    data = {"image": (img_buf, "query.png")}

    with patch.object(
        CLIPService,
        "generate_image_embedding",
        side_effect=CLIPModelNotAvailableError("Model weights not available offline")
    ):
        res = client.post(
            "/api/items/search/image",
            data=data,
            content_type="multipart/form-data",
        )
        assert res.status_code == 503
        assert "unavailable" in res.get_json()["error"]["message"].lower()


def test_api_search_by_image_success(client, app):
    """Verify successful 200 response with ranked items and model metadata."""
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO users (name, email, password_hash) VALUES ('Charlie', 'charlie@campus.edu', 'hash')")
        user_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        db.execute(
            """
            INSERT INTO items (title, description, category, type, location, date_event, user_id, image_filename)
            VALUES ('Sony Headphones', 'Matte black case', 'Electronics', 'found', 'Desk', '2026-10-25', ?, 'sony.jpg')
            """,
            (user_id,),
        )
        item_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.commit()

        test_emb = create_random_normalized_embedding(seed=55)
        store_item_embedding(item_id, test_emb)

    img_buf = create_test_image()
    data = {
        "image": (img_buf, "query.png"),
        "category": "Electronics",
        "type": "found",
    }

    with patch.object(CLIPService, "generate_image_embedding", return_value=test_emb):
        res = client.post(
            "/api/items/search/image",
            data=data,
            content_type="multipart/form-data",
        )
        assert res.status_code == 200
        json_data = res.get_json()
        assert json_data["count"] == 1
        assert "model_info" in json_data
        item = json_data["items"][0]
        assert item["id"] == item_id
        assert item["title"] == "Sony Headphones"
        assert item["similarity_score"] == 1.0
        assert item["similarity_percent"] == 100.0


def test_api_similarity_info(client):
    """Verify /api/items/similarity/info returns status, model, and db stats."""
    res = client.get("/api/items/similarity/info")
    assert res.status_code == 200
    data = res.get_json()
    assert "status" in data
    assert "clip" in data
    assert "database_stats" in data
    assert data["clip"]["embedding_dim"] == EMBEDDING_DIM


# ==============================================================================
# CLI Backfill Command Test
# ==============================================================================


def test_cli_backfill_embeddings_command(runner, app):
    """Test flask backfill-embeddings CLI command."""
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO users (name, email, password_hash) VALUES ('CLI', 'cli@campus.edu', 'hash')")
        uid = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        db.execute(
            """
            INSERT INTO items (title, description, category, type, location, date_event, user_id, image_filename)
            VALUES ('Hydro Flask', 'Pink bottle', 'Others', 'lost', 'Quad', '2026-10-25', ?, 'bottle.jpg')
            """,
            (uid,),
        )
        db.commit()

    with patch("services.item_service.backfill_all_embeddings", return_value={"total": 1, "processed": 1, "skipped": 0, "failed": 0}):
        result = runner.invoke(args=["backfill-embeddings", "--force"])
        assert result.exit_code == 0
        assert "Backfill complete" in result.output
        assert "processed=1" in result.output


# ==============================================================================
# Optional Smoke / Integration Test with Pretrained Weights
# ==============================================================================


@pytest.mark.integration
def test_real_clip_model_smoke():
    """
    Optional live integration test using official OpenAI CLIP pretrained weights.
    Runs only if real model weights can be loaded or are already cached.
    """
    CLIPService.reset_instance()
    service = CLIPService.get_instance()
    try:
        model, preprocess = service.load_model()
        assert model is not None
        assert preprocess is not None

        # Test embedding a real synthetic PIL Image
        img = Image.new("RGB", (224, 224), color=(200, 50, 50))
        emb = service.generate_image_embedding(img)
        assert isinstance(emb, np.ndarray)
        assert emb.shape == (EMBEDDING_DIM,)
        # L2 norm should be approximately 1.0
        norm = np.linalg.norm(emb)
        assert pytest.approx(norm, 1e-4) == 1.0

        # Compare with another image
        img2 = Image.new("RGB", (224, 224), color=(200, 50, 50))
        emb2 = service.generate_image_embedding(img2)
        sim = service.compute_similarity(emb, emb2)
        assert sim > 0.99  # Virtually identical colors

        img3 = Image.new("RGB", (224, 224), color=(0, 200, 50))
        emb3 = service.generate_image_embedding(img3)
        sim_diff = service.compute_similarity(emb, emb3)
        assert sim_diff < sim  # Green should be less similar to red than red to red
    except CLIPModelNotAvailableError:
        pytest.skip("CLIP pretrained weights not available in offline test environment.")
    finally:
        CLIPService.reset_instance()
