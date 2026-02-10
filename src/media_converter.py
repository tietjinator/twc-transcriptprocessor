"""
Media Converter - Converts any audio/video file to WAV for Whisper
"""

import subprocess
import json
from pathlib import Path
from typing import Optional, Dict, Any
from config import AUDIO_SAMPLE_RATE, AUDIO_CHANNELS, AUDIO_FORMAT, TEMP_DIR


class MediaConverter:
    """Converts media files to WAV format using FFmpeg"""

    def __init__(self):
        self.temp_dir = TEMP_DIR
        self.ffmpeg_path = self._find_ffmpeg()
        self.ffprobe_path = self._find_ffprobe()

    def _find_ffmpeg(self) -> str:
        """Find FFmpeg executable in common locations"""
        ffmpeg_paths = [
            'ffmpeg',  # Try PATH first
            '/opt/homebrew/bin/ffmpeg',  # Homebrew on Apple Silicon
            '/usr/local/bin/ffmpeg',  # Homebrew on Intel
            '/usr/bin/ffmpeg'  # System installation
        ]

        for ffmpeg_path in ffmpeg_paths:
            try:
                subprocess.run([ffmpeg_path, '-version'], capture_output=True, check=True, timeout=2)
                return ffmpeg_path
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                continue

        raise RuntimeError("FFmpeg not found. Please install FFmpeg.")

    def _find_ffprobe(self) -> str:
        """Find FFprobe executable in common locations"""
        ffprobe_paths = [
            'ffprobe',  # Try PATH first
            '/opt/homebrew/bin/ffprobe',  # Homebrew on Apple Silicon
            '/usr/local/bin/ffprobe',  # Homebrew on Intel
            '/usr/bin/ffprobe'  # System installation
        ]

        for ffprobe_path in ffprobe_paths:
            try:
                subprocess.run([ffprobe_path, '-version'], capture_output=True, check=True, timeout=2)
                return ffprobe_path
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                continue

        return 'ffprobe'  # Fallback to PATH

    def convert_to_wav(self, input_file: Path, progress_callback=None) -> Path:
        """
        Convert any audio/video file to WAV format

        Args:
            input_file: Path to input media file
            progress_callback: Optional callback function for progress updates

        Returns:
            Path to converted WAV file
        """
        if progress_callback:
            progress_callback(f"Converting {input_file.name} to WAV...")

        # Create output filename
        output_file = self.temp_dir / f"{input_file.stem}_converted.wav"

        # FFmpeg command to extract audio and convert to WAV
        cmd = [
            self.ffmpeg_path,
            '-i', str(input_file),
            '-ar', str(AUDIO_SAMPLE_RATE),
            '-ac', str(AUDIO_CHANNELS),
            '-c:a', AUDIO_FORMAT,
            '-y',  # Overwrite output file
            str(output_file)
        ]

        try:
            # Run FFmpeg with stderr capture for progress
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                text=True
            )

            if progress_callback:
                progress_callback(f"✓ Converted to WAV: {output_file.name}")

            return output_file

        except subprocess.CalledProcessError as e:
            error_msg = f"FFmpeg conversion failed: {e.stderr}"
            if progress_callback:
                progress_callback(f"✗ {error_msg}")
            raise RuntimeError(error_msg)

    def get_media_duration(self, file_path: Path) -> Optional[float]:
        """
        Get duration of media file in seconds

        Args:
            file_path: Path to media file

        Returns:
            Duration in seconds, or None if unable to determine
        """
        cmd = [
            self.ffprobe_path,
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(file_path)
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError):
            return None

    def get_media_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Extract metadata from media file (ID3 tags, etc.)

        Args:
            file_path: Path to media file

        Returns:
            Dictionary of metadata tags, or empty dict if none found
        """
        cmd = [
            self.ffprobe_path,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            str(file_path)
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)

            # Extract format tags (ID3, etc.)
            metadata = {}
            if 'format' in data and 'tags' in data['format']:
                tags = data['format']['tags']

                # Common metadata fields (normalize keys to lowercase)
                for key, value in tags.items():
                    # Store with original key name
                    metadata[key] = value

            return metadata

        except (subprocess.CalledProcessError, ValueError, json.JSONDecodeError):
            return {}

    def cleanup_temp_file(self, file_path: Path):
        """Remove temporary file"""
        try:
            if file_path.exists():
                file_path.unlink()
        except Exception:
            pass  # Ignore cleanup errors
