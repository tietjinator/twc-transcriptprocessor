"""
Parakeet-MLX ASR Client
Local speech-to-text using NVIDIA Parakeet optimized for Apple Silicon
"""

import logging
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ParakeetClient:
    """Client for Parakeet-MLX ASR (local Apple Silicon transcription)"""

    def __init__(self):
        """Initialize Parakeet-MLX model"""
        self.model = None

    def _load_model(self):
        """Lazy-load the model on first use"""
        if self.model is None:
            logger.debug("Loading Parakeet-MLX model...")
            from parakeet_mlx import from_pretrained
            self.model = from_pretrained("mlx-community/parakeet-tdt-0.6b-v3")
            logger.debug("Parakeet-MLX model loaded successfully")

    def transcribe(self, audio_path: Path) -> str:
        """
        Transcribe audio file using Parakeet-MLX

        Args:
            audio_path: Path to audio file (WAV format)

        Returns:
            Transcribed text

        Raises:
            RuntimeError: If transcription fails
        """
        try:
            self._load_model()

            logger.debug(f"Transcribing with Parakeet-MLX: {audio_path}")

            # Optimal settings for 40-minute audio files:
            # - 120s chunks (default) for speed
            # - greedy decoding (default) for speed
            # - bfloat16 (default) for Apple Silicon
            # - 15s overlap (default) for accuracy at chunk boundaries
            result = self.model.transcribe(
                str(audio_path),
                chunk_duration=120.0,  # 2-minute chunks (optimal)
                overlap_duration=15.0   # 15-second overlap
            )

            logger.debug(f"Transcription complete: {len(result.text)} characters")
            return result.text

        except Exception as e:
            error_msg = f"Parakeet-MLX transcription failed: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def test_connection(self) -> bool:
        """
        Test if Parakeet-MLX is available and working

        Returns:
            True if available, False otherwise
        """
        try:
            from parakeet_mlx import from_pretrained
            # Just check if we can import - actual model loading happens on first use
            return True
        except Exception as e:
            logger.error(f"Parakeet-MLX not available: {str(e)}")
            return False
