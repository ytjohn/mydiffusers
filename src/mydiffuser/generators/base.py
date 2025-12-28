"""Base class for generation backends."""

import gc
import logging
from abc import ABC, abstractmethod
from typing import Any

import torch

logger = logging.getLogger(__name__)


class BaseGenerator(ABC):
    """Abstract base class for all generators.

    Subclasses must implement:
    - load_model(): Load the model into memory
    - warmup(): Run a warmup inference

    Note: generate() signature varies by generator type, so it's not
    defined here. Subclasses should define their own typed generate() method.
    """

    def __init__(self) -> None:
        self._model: Any = None
        self._is_loaded = False

    @property
    def is_loaded(self) -> bool:
        """Check if the model is loaded and ready."""
        return self._is_loaded

    @abstractmethod
    def load_model(self) -> None:
        """Load the model into memory.

        Should set self._model and self._is_loaded = True on success.
        """

    @abstractmethod
    def warmup(self) -> None:
        """Run a warmup inference to prime the model.

        Called after load_model() to ensure first real request is snappy.
        """

    def unload(self) -> None:
        """Unload the model and free GPU memory.

        Subclasses should override this to handle specific cleanup,
        calling super().unload() at the end.
        """
        if self._model is not None:
            # Move model to CPU first (helps release GPU memory)
            if hasattr(self._model, "to"):
                try:
                    self._model.to("cpu")
                except Exception:
                    pass  # Some models don't support .to()

            # Delete the model reference
            del self._model
            self._model = None

        self._is_loaded = False

        # Force garbage collection and clear GPU cache
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

        logger.info("%s unloaded", self.__class__.__name__)

    def ensure_loaded(self) -> None:
        """Ensure the model is loaded, raising if not."""
        if not self._is_loaded:
            raise RuntimeError(f"{self.__class__.__name__} model not loaded")
