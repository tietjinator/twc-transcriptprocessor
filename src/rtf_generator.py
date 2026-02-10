"""
RTF File Generator - Creates formatted RTF files from transcript data
"""

from pathlib import Path
from typing import Dict
import logging
import os

# Set up logging
logging.basicConfig(
    filename=os.path.expanduser('~/Library/Logs/TranscriptProcessor-Dev.log'),
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RTFGenerator:
    """Generates RTF files with proper formatting"""

    @staticmethod
    def create_rtf(data: Dict, output_path: Path) -> None:
        """
        Create RTF file with formatted transcript

        Args:
            data: Dict containing:
                - summary: str
                - broad_keywords: list
                - specific_keywords: list
                - scripture_references: list
                - context_notes: str
                - formatted_transcript: str
                - speaker_name: str
            output_path: Path where RTF file should be saved
        """
        # RTF header
        rtf_content = r"""{\rtf1\ansi\deff0
{\fonttbl{\f0\fmodern\fcharset0 Courier New;}}
{\colortbl;\red0\green0\blue0;}
\viewkind4\uc1\pard\f0\fs22
"""

        # AI-Generated Transcript Notice (Bold + Italic - entire section)
        rtf_content += r"""\b\i\fs24 ⚠️  AI-GENERATED TRANSCRIPT\b0\i0\fs22\par
\b\i This transcript was created using Whisper AI and Claude Haiku and has not been manually verified. Some words, names, and technical terms may be inaccurate. Please refer to the audio file for verification of critical details.\b0\i0\par
\par
\par
"""

        # File Metadata (always show section)
        file_metadata = data.get('file_metadata', {})
        rtf_content += r"\b\fs24 FILE METADATA\b0\fs22\par\par"

        # Debug: Log what we actually have
        logger.debug(f"file_metadata type: {type(file_metadata)}")
        logger.debug(f"file_metadata contents: {file_metadata}")
        logger.debug(f"file_metadata bool: {bool(file_metadata)}")

        if file_metadata:
            for key, value in file_metadata.items():
                # Format key nicely (capitalize, replace underscores)
                display_key = key.replace('_', ' ').title()
                logger.debug(f"Rendering metadata: {display_key} = {value}")
                rtf_content += r"\b " + RTFGenerator._escape_rtf(display_key) + r":\b0\~"
                rtf_content += RTFGenerator._escape_rtf(str(value)) + r"\par"
        else:
            rtf_content += r"No metadata found in file\par"
        rtf_content += r"\par\par"

        # Summary (Bold Header)
        rtf_content += r"\b\fs24 SUMMARY\b0\fs22\par\par"
        rtf_content += RTFGenerator._escape_rtf(data['summary']) + r"\par\par\par"

        # Broad Keywords (Bold Header)
        rtf_content += r"\b\fs24 BROAD KEYWORDS\b0\fs22\par\par"
        for keyword in data['broad_keywords']:
            rtf_content += r"\bullet\~" + RTFGenerator._escape_rtf(keyword) + r"\par"
        rtf_content += r"\par\par"

        # Specific Keywords (Bold Header)
        rtf_content += r"\b\fs24 SPECIFIC KEYWORDS\b0\fs22\par\par"
        for keyword in data['specific_keywords']:
            rtf_content += r"\bullet\~" + RTFGenerator._escape_rtf(keyword) + r"\par"
        rtf_content += r"\par\par"

        # Scripture References (Bold Header)
        rtf_content += r"\b\fs24 SCRIPTURE REFERENCES\b0\fs22\par\par"
        if data.get('scripture_references'):
            for reference in data['scripture_references']:
                rtf_content += r"\bullet\~" + RTFGenerator._escape_rtf(reference) + r"\par"
        else:
            rtf_content += r"None mentioned\par"
        rtf_content += r"\par\par"

        # Context Notes (Bold Header)
        rtf_content += r"\b\fs24 CONTEXT NOTES\b0\fs22\par\par"
        rtf_content += RTFGenerator._escape_rtf(data['context_notes']) + r"\par"
        rtf_content += r"\par\par"

        # Separator
        rtf_content += r"_______________________________________________________________________________\par\par\par"

        # Full Transcript Header
        rtf_content += r"\b\fs24 FULL TRANSCRIPT\b0\fs22\par\par"

        # Main Transcript (No bold, just the text)
        rtf_content += r"\fs22 "
        # Replace paragraph breaks with RTF paragraph marks
        transcript_paragraphs = data['formatted_transcript'].split('\n\n')
        for i, para in enumerate(transcript_paragraphs):
            if para.strip():
                # Add paragraph default reset before each new paragraph (except first)
                if i > 0:
                    rtf_content += r"\pard\fs22 "
                rtf_content += RTFGenerator._escape_rtf(para.strip()) + r"\par\par"

        # Close RTF document
        rtf_content += r"}"

        # Write to file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(rtf_content)

    @staticmethod
    def _escape_rtf(text: str) -> str:
        """
        Escape special characters for RTF format

        Args:
            text: Plain text to escape

        Returns:
            RTF-escaped text
        """
        # Replace backslashes first
        text = text.replace('\\', '\\\\')
        # Replace curly braces
        text = text.replace('{', '\\{')
        text = text.replace('}', '\\}')
        # Replace line breaks within paragraphs with space
        text = text.replace('\n', ' ')
        return text

    @staticmethod
    def create_filename(original_filename: str, speaker_name: str, file_id: str = "") -> str:
        """
        Create standardized filename for cleaned transcript

        Args:
            original_filename: Original media file name
            speaker_name: Speaker name from transcript
            file_id: Optional file ID/number

        Returns:
            Formatted filename
        """
        # Extract title from filename (remove extension and ID)
        title = Path(original_filename).stem

        # Clean up title (remove common patterns like numbers at end)
        import re
        title = re.sub(r'-\d+$', '', title)  # Remove trailing numbers
        title = title.replace('_', ' ').strip()

        # Build filename
        if file_id:
            filename = f"{title} - {speaker_name}-{file_id}_CLEANED.rtf"
        else:
            filename = f"{title} - {speaker_name}_CLEANED.rtf"

        return filename

    @staticmethod
    def get_speaker_folder(speaker_name: str, base_path: Path) -> Path:
        """
        Get or create speaker subfolder

        Args:
            speaker_name: Speaker name
            base_path: Base directory for transcripts

        Returns:
            Path to speaker subfolder
        """
        # Clean speaker name for folder
        safe_name = speaker_name.replace('/', '-').replace('\\', '-')
        folder_path = base_path / safe_name
        folder_path.mkdir(parents=True, exist_ok=True)
        return folder_path
