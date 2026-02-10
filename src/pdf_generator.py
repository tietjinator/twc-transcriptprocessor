"""
PDF File Generator - Creates formatted PDF files from transcript data
Uses WeasyPrint for reliable paragraph selection and text flow.
"""

from pathlib import Path
from typing import Dict
import html
import re
from config import ARCHIVES_LOGO_PATH_OR_URL, ARCHIVES_FOOTER_TEXT, PROJECT_ROOT


class PDFGenerator:
    """Generates PDF files with proper formatting using HTML/CSS"""

    @staticmethod
    def _strip_emoji(text: str) -> str:
        if not text:
            return ""
        # Basic emoji/symbol ranges
        return re.sub(
            r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U0001F1E6-\U0001F1FF]",
            "",
            text
        )

    @staticmethod
    def _escape(text: str) -> str:
        return html.escape(text or "")

    @staticmethod
    def _resolve_logo_src() -> str:
        """Return a usable logo src for WeasyPrint (file:// or https://)."""
        value = (ARCHIVES_LOGO_PATH_OR_URL or "").strip()
        if not value:
            return ""
        if value.startswith("http://") or value.startswith("https://"):
            return value
        path = Path(value).expanduser()
        if path.exists():
            return path.resolve().as_uri()
        return ""

    @staticmethod
    def _font_uri(filename: str) -> str:
        path = PROJECT_ROOT / "assets" / "fonts" / filename
        if path.exists():
            return path.resolve().as_uri()
        return ""

    @staticmethod
    def create_pdf(data: Dict, output_path: Path) -> None:
        """
        Create PDF file with formatted transcript

        Args:
            data: Dict containing:
                - summary: str
                - broad_keywords: list
                - specific_keywords: list
                - scripture_references: list
                - context_notes: str
                - formatted_transcript: str
                - speaker_name: str
                - file_metadata: dict (optional)
            output_path: Path where PDF file should be saved
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        engine_info = data.get('engine_info', {})
        transcription_engine = PDFGenerator._strip_emoji(engine_info.get('transcription', 'Whisper AI'))
        formatting_engine = PDFGenerator._strip_emoji(engine_info.get('formatting', 'Claude Haiku 3.5'))
        metadata_engine = PDFGenerator._strip_emoji(engine_info.get('metadata', 'Claude Haiku 4.5'))

        file_metadata = data.get('file_metadata', {})
        filtered_metadata = {}
        allowed_keys = {
            'title': 'Title',
            'artist': 'Artist',
            'album': 'Album',
            'date': 'Date',
            'genre': 'Genre',
            'comment': 'Comment'
        }
        for key, value in file_metadata.items():
            if not value or value == "????" or str(value).strip() == "":
                continue
            key_lower = str(key).strip().lower()
            if key_lower not in allowed_keys:
                continue
            display_key = allowed_keys[key_lower]
            filtered_metadata[display_key] = PDFGenerator._strip_emoji(str(value))

        def render_bullets(items):
            if not items:
                return "<p class='body'>None mentioned</p>"
            return "<ul>" + "".join(f"<li>{PDFGenerator._escape(PDFGenerator._strip_emoji(str(i)))}</li>" for i in items) + "</ul>"

        transcript_paragraphs = [
            p.strip() for p in data['formatted_transcript'].split('\n\n') if p.strip()
        ]
        transcript_html = "\n".join(
            f"<p class='transcript'>{PDFGenerator._escape(p)}</p>" for p in transcript_paragraphs
        )

        meta_html = (
            "<p class='body'>No metadata found in file</p>"
            if not filtered_metadata
            else "".join(
                f"<p class='body'><strong>{PDFGenerator._escape(PDFGenerator._strip_emoji(str(k)))}:</strong> {PDFGenerator._escape(str(v))}</p>"
                for k, v in filtered_metadata.items()
            )
        )

        logo_src = PDFGenerator._resolve_logo_src()
        footer_text = PDFGenerator._strip_emoji(ARCHIVES_FOOTER_TEXT)
        logo_html = ""
        if logo_src:
            logo_html = f"<img class='logo' src='{PDFGenerator._escape(logo_src)}' alt='Wesleyan Archives' />"

        font_regular = PDFGenerator._font_uri("SourceSans3-VariableFont_wght.ttf")
        font_italic = PDFGenerator._font_uri("SourceSans3-Italic-VariableFont_wght.ttf")

        html_doc = f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <style>
      @font-face {{
        font-family: "Source Sans 3";
        src: url("{PDFGenerator._escape(font_regular)}");
        font-weight: 100 900;
        font-style: normal;
      }}
      @font-face {{
        font-family: "Source Sans 3";
        src: url("{PDFGenerator._escape(font_italic)}");
        font-weight: 100 900;
        font-style: italic;
      }}
      @page {{
        size: Letter;
        margin: 0.75in;
        @bottom-left {{
          content: "{PDFGenerator._escape(footer_text)}";
          font-size: 9pt;
          color: #6b6b6b;
        }}
        @bottom-right {{
          content: "Page " counter(page) " of " counter(pages);
          font-size: 9pt;
          color: #6b6b6b;
        }}
      }}
      @page:first {{
        margin-top: 0.25in;
      }}
      body {{
        font-family: "Source Sans 3", "Helvetica Neue", Arial, sans-serif;
        color: #1d1d1f;
        font-size: 11pt;
        line-height: 1.35;
      }}
      header {{
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 0 0 6pt 0;
      }}
      .logo {{
        height: 75px;
        width: auto;
      }}
      h1 {{
        font-size: 13.5pt;
        margin: 16pt 0 6pt;
        font-weight: 700;
      }}
      .warning-title {{
        font-size: 11pt;
        font-weight: 700;
        color: #E96351;
        margin-bottom: 4pt;
      }}
      .warning-body {{
        font-size: 10.5pt;
        font-style: italic;
        margin-bottom: 12pt;
      }}
      .body {{
        margin: 0 0 6pt 0;
      }}
      ul {{
        margin: 0 0 8pt 18pt;
        padding: 0;
      }}
      li {{
        margin: 0 0 3pt 0;
      }}
      hr {{
        border: none;
        border-top: 1px solid #c7c7c7;
        margin: 12pt 0;
      }}
      .transcript {{
        font-size: 10.5pt;
        margin: 0 0 8pt 0;
      }}
      .footer {{
        display: none;
      }}
    </style>
  </head>
  <body>
    <header>
      {logo_html}
    </header>
    <div class="warning-title">CAUTION: AI-GENERATED TRANSCRIPT</div>
    <div class="warning-body">
      This transcript was created using {PDFGenerator._escape(transcription_engine)} for transcription,
      {PDFGenerator._escape(formatting_engine)} for formatting, and {PDFGenerator._escape(metadata_engine)} for metadata extraction.
      It has not been manually verified. Some words, names, and technical terms may be inaccurate.
      Please refer to the audio file for verification of critical details.
    </div>

    <h1>FILE METADATA</h1>
    {meta_html}

    <h1>SUMMARY</h1>
    <p class="body">{PDFGenerator._escape(PDFGenerator._strip_emoji(data['summary']))}</p>

    <h1>BROAD KEYWORDS</h1>
    {render_bullets(data['broad_keywords'])}

    <h1>SPECIFIC KEYWORDS</h1>
    {render_bullets(data['specific_keywords'])}

    <h1>SCRIPTURE REFERENCES</h1>
    {render_bullets(data.get('scripture_references', []))}

    <h1>CONTEXT NOTES</h1>
    <p class="body">{PDFGenerator._escape(PDFGenerator._strip_emoji(data['context_notes']))}</p>

    <hr />

    <h1>FULL TRANSCRIPT</h1>
    {transcript_html}
  </body>
</html>
"""

        # Import here so the app can launch and show setup prompts if WeasyPrint
        # isn't installed yet.
        from weasyprint import HTML
        HTML(string=html_doc).write_pdf(str(output_path))

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
            filename = f"{title} - {speaker_name}-{file_id}_CLEANED.pdf"
        else:
            filename = f"{title} - {speaker_name}_CLEANED.pdf"

        return filename
