"""
services/clip_service.py
OpenAI CLIP (Contrastive Language-Image Pre-training) Service.

Features:
- Lazy singleton model loader with thread safety
- Automatic device detection (CUDA, Apple Silicon MPS, or CPU)
- Robust image validation (MIME, magic bytes, Pillow integrity, decompression bomb guards)
- Embedding generation and L2 normalization
- Cosine similarity calculation
- Binary serialization for SQLite storage
- Graceful error handling for missing dependencies, network/cache issues, and corrupt files
"""

import io
import logging
import os
import threading
from typing import Optional, Tuple, Union

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Constants
DEFAULT_CLIP_MODEL = "ViT-B/32"
EMBEDDING_DIM = 512
MAX_IMAGE_PIXELS = 25_000_000  # Guard against decompression bomb attacks
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_PIL_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


class CLIPServiceError(Exception):
    """Base exception for CLIP service errors."""
    pass


class CLIPModelNotAvailableError(CLIPServiceError):
    """Raised when the CLIP model cannot be loaded or initialized."""
    pass


class InvalidImageError(CLIPServiceError):
    """Raised when an image fails decoding or validation checks."""
    pass


def get_optimal_device() -> Tuple[str, str]:
    """
    Detect the optimal PyTorch compute device available on this machine.
    Returns (device_str, device_description).
    """
    try:
        import torch

        # 1. NVIDIA CUDA
        if torch.cuda.is_available():
            dev_name = torch.cuda.get_device_name(0) if torch.cuda.device_count() > 0 else "CUDA"
            return "cuda", f"NVIDIA GPU ({dev_name})"

        # 2. Apple Silicon MPS (Metal Performance Shaders)
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            # Verify MPS can actually allocate and execute an operation
            try:
                test_tensor = torch.zeros(1, device="mps")
                del test_tensor
                return "mps", "Apple Silicon GPU (Metal MPS)"
            except Exception as mps_err:
                logger.warning("MPS available but initialization test failed: %s. Falling back to CPU.", mps_err)

        # 3. Standard CPU fallback
        return "cpu", "Standard CPU"
    except Exception as exc:
        logger.warning("Error checking PyTorch accelerator: %s. Defaulting to CPU.", exc)
        return "cpu", "Standard CPU (fallback)"


class CLIPService:
    """
    Thread-safe singleton service for loading OpenAI CLIP and generating image embeddings.
    """
    _instance: Optional["CLIPService"] = None
    _lock = threading.Lock()

    def __init__(self, model_name: str = DEFAULT_CLIP_MODEL, cache_dir: Optional[str] = None):
        self.model_name = model_name
        self.cache_dir = cache_dir or os.environ.get(
            "CLIP_CACHE_DIR",
            os.path.expanduser("~/.cache/clip")
        )
        self.device_str, self.device_name = get_optimal_device()
        self._model = None
        self._preprocess = None
        self._is_loaded = False
        self._load_error: Optional[str] = None

    @classmethod
    def get_instance(cls, model_name: str = DEFAULT_CLIP_MODEL) -> "CLIPService":
        """Thread-safe access to the singleton CLIPService instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(model_name=model_name)
            return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset the singleton instance (primarily used for unit testing)."""
        with cls._lock:
            cls._instance = None

    def get_info(self) -> dict:
        """Return runtime status, device information, and model metadata."""
        return {
            "model_name": self.model_name,
            "model_version": f"openai/clip-{self.model_name.lower().replace('/', '-')}",
            "device": self.device_str,
            "device_description": self.device_name,
            "cache_dir": self.cache_dir,
            "is_loaded": self._is_loaded,
            "load_error": self._load_error,
            "embedding_dim": EMBEDDING_DIM,
        }

    def load_model(self):
        """
        Lazily load the official OpenAI CLIP model and preprocessing pipeline.
        Thread-safe; only downloads and loads weights once.
        """
        if self._is_loaded and self._model is not None:
            return self._model, self._preprocess

        with self._lock:
            # Double-check locking
            if self._is_loaded and self._model is not None:
                return self._model, self._preprocess

            try:
                import clip
                import torch
            except ImportError as err:
                msg = f"CLIP dependencies missing: {err}. Please install torch and clip."
                self._load_error = msg
                logger.error(msg)
                raise CLIPModelNotAvailableError(msg) from err

            try:
                os.makedirs(self.cache_dir, exist_ok=True)
                logger.info(
                    "Loading OpenAI CLIP model '%s' on %s (cache: %s)...",
                    self.model_name,
                    self.device_str,
                    self.cache_dir,
                )
                model, preprocess = clip.load(
                    self.model_name,
                    device=self.device_str,
                    download_root=self.cache_dir,
                )
                model.eval()
                self._model = model
                self._preprocess = preprocess
                self._is_loaded = True
                self._load_error = None
                logger.info("OpenAI CLIP model successfully loaded on %s.", self.device_str)
                return self._model, self._preprocess
            except Exception as err:
                # If loading on MPS fails, attempt fallback to CPU
                if self.device_str == "mps":
                    logger.warning("Failed to load CLIP on MPS (%s). Retrying on CPU...", err)
                    try:
                        self.device_str = "cpu"
                        self.device_name = "Standard CPU (MPS fallback)"
                        model, preprocess = clip.load(
                            self.model_name,
                            device="cpu",
                            download_root=self.cache_dir,
                        )
                        model.eval()
                        self._model = model
                        self._preprocess = preprocess
                        self._is_loaded = True
                        self._load_error = None
                        logger.info("OpenAI CLIP model successfully loaded on CPU fallback.")
                        return self._model, self._preprocess
                    except Exception as cpu_err:
                        err = cpu_err

                msg = f"Failed to load CLIP model '{self.model_name}': {err}"
                self._load_error = msg
                logger.error(msg, exc_info=True)
                raise CLIPModelNotAvailableError(msg) from err

    @staticmethod
    def validate_and_open_image(image_input: Union[str, bytes, io.BytesIO, Image.Image]) -> Image.Image:
        """
        Safely validate and open an image input.
        Guards against decompression bombs, unsupported formats, and truncated files.
        Returns a PIL Image in RGB mode.
        """
        # Configure PIL limits
        Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

        if isinstance(image_input, Image.Image):
            pil_img = image_input.copy()
        elif isinstance(image_input, str):
            if not os.path.isfile(image_input):
                raise InvalidImageError(f"Image file does not exist at path: {image_input}")
            size = os.path.getsize(image_input)
            if size > MAX_IMAGE_BYTES:
                raise InvalidImageError(f"Image file exceeds maximum limit of {MAX_IMAGE_BYTES // (1024 * 1024)} MB.")
            try:
                pil_img = Image.open(image_input)
                pil_img.load()  # Ensure image bytes are read
            except Exception as err:
                raise InvalidImageError(f"Invalid image file: {err}") from err
        elif isinstance(image_input, (bytes, bytearray)):
            if len(image_input) > MAX_IMAGE_BYTES:
                raise InvalidImageError(f"Image byte size exceeds maximum limit of {MAX_IMAGE_BYTES // (1024 * 1024)} MB.")
            try:
                pil_img = Image.open(io.BytesIO(image_input))
                pil_img.load()
            except Exception as err:
                raise InvalidImageError(f"Invalid image content: {err}") from err
        elif hasattr(image_input, "read"):
            # File-like object (e.g., FileStorage or BytesIO)
            try:
                content = image_input.read()
                if hasattr(image_input, "seek"):
                    image_input.seek(0)
                if len(content) > MAX_IMAGE_BYTES:
                    raise InvalidImageError(f"Image file exceeds maximum limit of {MAX_IMAGE_BYTES // (1024 * 1024)} MB.")
                pil_img = Image.open(io.BytesIO(content))
                pil_img.load()
            except InvalidImageError:
                raise
            except Exception as err:
                raise InvalidImageError(f"Invalid or corrupted image upload: {err}") from err
        else:
            raise InvalidImageError("Unsupported image input type.")

        # Validate format
        fmt = (pil_img.format or "").upper()
        if fmt and fmt not in ALLOWED_PIL_FORMATS:
            allowed = ", ".join(sorted(ALLOWED_PIL_FORMATS))
            raise InvalidImageError(f"Unsupported image format '{fmt}'. Allowed formats: {allowed}")

        # Convert to RGB (handles RGBA, P, L, CMYK)
        try:
            if pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")
        except Exception as err:
            raise InvalidImageError(f"Failed to convert image color mode: {err}") from err

        return pil_img

    def generate_image_embedding(
        self,
        image_input: Union[str, bytes, io.BytesIO, Image.Image]
    ) -> np.ndarray:
        """
        Generate a normalized 512-dimensional CLIP embedding for an image.
        Returns a 1D float32 numpy array with L2 norm = 1.0.
        """
        pil_img = self.validate_and_open_image(image_input)
        model, preprocess = self.load_model()

        import torch

        try:
            # Preprocess image into PyTorch tensor: (3, 224, 224)
            image_tensor = preprocess(pil_img).unsqueeze(0).to(self.device_str)

            with torch.no_grad():
                # Extract raw visual features
                features = model.encode_image(image_tensor)

                # Safe L2 Normalization
                norm = features.norm(dim=-1, keepdim=True)
                if (
                    norm is None
                    or torch.isnan(norm).any()
                    or torch.isinf(norm).any()
                    or norm.item() <= 1e-12
                ):
                    raise ValueError("Computed image embedding has invalid zero or non-finite norm.")

                normalized_features = features / norm

            # Convert to 1D float32 numpy array
            emb_np = normalized_features.squeeze(0).cpu().numpy().astype(np.float32)

            # Ensure correct dimension
            if emb_np.ndim != 1 or len(emb_np) != EMBEDDING_DIM:
                raise ValueError(f"Expected embedding shape ({EMBEDDING_DIM},), got {emb_np.shape}")

            return emb_np
        except Exception as err:
            if isinstance(err, (CLIPServiceError, ValueError)):
                raise
            raise CLIPServiceError(f"Inference error during embedding generation: {err}") from err

    @staticmethod
    def compute_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
        """
        Compute cosine similarity between two normalized embeddings.
        Because both embeddings are L2-normalized, cosine similarity equals the dot product.
        Returns a float clamped to [-1.0, 1.0].
        """
        if emb1 is None or emb2 is None:
            return 0.0

        try:
            v1 = np.asarray(emb1, dtype=np.float32).ravel()
            v2 = np.asarray(emb2, dtype=np.float32).ravel()

            if len(v1) == 0 or len(v2) == 0 or len(v1) != len(v2):
                return 0.0

            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)

            if norm1 <= 1e-12 or norm2 <= 1e-12 or np.isnan(norm1) or np.isnan(norm2):
                return 0.0

            # Normalize if not already strictly unit norm
            v1_unit = v1 / norm1
            v2_unit = v2 / norm2

            sim = float(np.dot(v1_unit, v2_unit))
            # Clamp to range [-1.0, 1.0] to guard against tiny float precision drift
            return max(-1.0, min(1.0, sim))
        except Exception as exc:
            logger.warning("Error computing cosine similarity: %s", exc)
            return 0.0

    @staticmethod
    def embedding_to_blob(embedding: np.ndarray) -> bytes:
        """Serialize a float32 numpy array to raw bytes for SQLite storage."""
        if embedding is None:
            raise ValueError("Cannot serialize None embedding")
        arr = np.asarray(embedding, dtype=np.float32).ravel()
        return arr.tobytes()

    @staticmethod
    def blob_to_embedding(blob: bytes) -> np.ndarray:
        """Deserialize raw bytes from SQLite into a float32 numpy array."""
        if not blob:
            raise ValueError("Cannot deserialize empty blob")
        arr = np.frombuffer(blob, dtype=np.float32).copy()
        if len(arr) != EMBEDDING_DIM:
            raise ValueError(f"Invalid embedding dimension in blob: expected {EMBEDDING_DIM}, got {len(arr)}")
        return arr
