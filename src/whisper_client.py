"""
Whisper.cpp API Client
"""

import requests
import socket
import json
from pathlib import Path
from typing import Optional
from config import WHISPER_URL, WHISPER_HOST, WHISPER_PORT


class WhisperClient:
    """Client for whisper.cpp transcription service"""

    def __init__(self):
        # Try to load from whisper.json config file first
        project_config = Path(__file__).resolve().parent.parent / "config" / "whisper.json"
        home_config = Path.home() / "TranscriptProcessor" / "config" / "whisper.json"

        if project_config.exists():
            with open(project_config, 'r') as f:
                config = json.load(f)
                self.host = config.get('host', WHISPER_HOST)
                self.port = config.get('port', WHISPER_PORT)
                self.url = f"http://{self.host}:{self.port}/inference"
        elif home_config.exists():
            with open(home_config, 'r') as f:
                config = json.load(f)
                self.host = config.get('host', WHISPER_HOST)
                self.port = config.get('port', WHISPER_PORT)
                self.url = f"http://{self.host}:{self.port}/inference"
        else:
            # Fall back to config.py defaults
            self.url = WHISPER_URL
            self.host = WHISPER_HOST
            self.port = WHISPER_PORT

    def check_connection(self) -> bool:
        """
        Check if whisper.cpp service is reachable

        Returns:
            True if service is reachable, False otherwise
        """
        try:
            # Try to connect to the host:port
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((self.host, self.port))
            sock.close()
            return result == 0
        except Exception:
            return False

    def transcribe(self, wav_file: Path, progress_callback=None) -> str:
        """
        Transcribe audio file using whisper.cpp service

        Args:
            wav_file: Path to WAV audio file
            progress_callback: Optional callback for progress updates

        Returns:
            Transcript text

        Raises:
            RuntimeError: If transcription fails
        """
        if progress_callback:
            progress_callback(f"Transcribing {wav_file.name}...")

        try:
            with open(wav_file, 'rb') as f:
                files = {'file': (wav_file.name, f, 'audio/wav')}

                response = requests.post(
                    self.url,
                    files=files,
                    timeout=600  # 10 minute timeout for long files
                )

            response.raise_for_status()
            result = response.json()

            if result.get('code') == 1 and 'data' in result:
                # Extract text from segments
                segments = result['data']
                transcript = ' '.join([seg['sentence'].strip() for seg in segments])

                if progress_callback:
                    progress_callback(f"✓ Transcription complete ({len(transcript)} characters)")

                return transcript

            else:
                error_msg = result.get('msg', 'Unknown error')
                raise RuntimeError(f"Transcription failed: {error_msg}")

        except requests.exceptions.RequestException as e:
            error_msg = f"API request failed: {str(e)}"
            if progress_callback:
                progress_callback(f"✗ {error_msg}")
            raise RuntimeError(error_msg)

    def get_connection_instructions(self) -> str:
        """
        Get instructions for connecting to the service

        Returns:
            User-friendly connection instructions
        """
        return f"""Unable to connect to transcription service at {self.host}:{self.port}

Please ensure:
1. You are connected to Tailscale
2. The whisper.cpp service is running at {self.host}:{self.port}

To connect via Tailscale:
- Open Tailscale from your menu bar
- Ensure you're connected to your network
- Verify the service is accessible

After connecting, please try again."""
