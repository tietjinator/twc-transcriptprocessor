"""
Main Transcript Processor - Orchestrates the complete workflow
"""

from pathlib import Path
from typing import Callable, Optional
import threading
import queue
import time
import os
from datetime import datetime
from media_converter import MediaConverter
from whisper_client import WhisperClient
from parakeet_client import ParakeetClient
from claude_formatter import ClaudeFormatter
from openai_formatter import OpenAIFormatter
from pdf_generator import PDFGenerator
from config import SUPPORTED_EXTENSIONS, TRANSCRIPTION_ENGINE_PARAKEET, TRANSCRIPTION_ENGINE_WHISPER


class TranscriptProcessor:
    """Main processor that coordinates all steps"""

    def __init__(self, anthropic_api_key: str):
        """
        Initialize processor

        Args:
            anthropic_api_key: Anthropic API key for Claude
        """
        self.converter = MediaConverter()
        self.whisper = WhisperClient()
        self.parakeet = ParakeetClient()
        self.claude = ClaudeFormatter(api_key=anthropic_api_key)
        self.pdf_gen = PDFGenerator()

        # Default preferences (can be overridden per-call)
        self.transcription_engine = TRANSCRIPTION_ENGINE_PARAKEET  # Default: Parakeet (local, fast)
        self.openai_formatting_model = "gpt-4o-mini"  # Default: GPT-4o mini (reliable paragraphing)
        self.openai_metadata_model = None  # Default: Claude Haiku 4.5 for metadata

    def check_services(self) -> dict:
        """
        Check if all required services are available

        Returns:
            Dict with service status:
            {
                "whisper": bool,
                "parakeet": bool,
                "claude": bool,
                "openai": bool,
                "ffmpeg": bool,
                "weasyprint": bool,
                "messages": list
            }
        """
        status = {
            "whisper": False,
            "parakeet": False,
            "claude": False,
            "openai": False,
            "ffmpeg": False,
            "weasyprint": False,
            "messages": []
        }

        # Check Parakeet-MLX availability (primary transcription engine)
        try:
            import parakeet_mlx  # noqa: F401
            status["parakeet"] = True
        except ImportError:
            status["parakeet"] = False
            status["messages"].append("Parakeet-MLX not installed - install with: ./venv/bin/pip install parakeet-mlx")

        # Check Whisper.cpp connection (optional, requires manual server setup)
        status["whisper"] = self.whisper.check_connection()
        if not status["whisper"]:
            status["messages"].append("Whisper.cpp not configured (optional - requires remote server)")

        # Check Claude API key (just verify it exists and is formatted correctly)
        try:
            from config import load_api_key
            claude_key = load_api_key()
            if claude_key and claude_key.startswith("sk-ant-"):
                status["claude"] = True
            else:
                status["claude"] = False
                status["messages"].append("Claude API key not found or invalid format")
        except Exception as e:
            status["claude"] = False
            status["messages"].append(f"Claude API key error: {str(e)}")

        # Check OpenAI API key (optional - just verify format)
        from config import load_openai_api_key
        openai_key = load_openai_api_key()
        if openai_key and openai_key.startswith("sk-"):
            status["openai"] = True
        else:
            status["openai"] = False
            status["messages"].append("OpenAI API key not configured - GPT models unavailable")

        # Check FFmpeg (try common installation paths)
        import subprocess
        import os
        ffmpeg_found = False
        ffmpeg_paths = [
            'ffmpeg',  # Try PATH first
            '/opt/homebrew/bin/ffmpeg',  # Homebrew on Apple Silicon
            '/usr/local/bin/ffmpeg',  # Homebrew on Intel
            '/usr/bin/ffmpeg'  # System installation
        ]

        for ffmpeg_path in ffmpeg_paths:
            try:
                subprocess.run([ffmpeg_path, '-version'], capture_output=True, check=True, timeout=2)
                status["ffmpeg"] = True
                ffmpeg_found = True
                break
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                continue

        if not ffmpeg_found:
            status["messages"].append("FFmpeg not found. Please install FFmpeg.")

        # Check WeasyPrint (may raise OSError if system libs are missing)
        try:
            import weasyprint  # noqa: F401
            status["weasyprint"] = True
        except Exception:
            status["messages"].append(
                "WeasyPrint not available (missing system libraries). PDF generation will fail."
            )

        return status

    def is_supported_file(self, file_path: Path) -> bool:
        """Check if file extension is supported"""
        return file_path.suffix.lower() in SUPPORTED_EXTENSIONS

    @staticmethod
    def _default_log_dir(media_files: list[Path]) -> Path:
        """Choose a stable log directory when no explicit output directory is provided."""
        if not media_files:
            return Path.cwd()

        parent_paths = [str(p.parent) for p in media_files]
        try:
            common = Path(os.path.commonpath(parent_paths))
            if common.exists():
                return common
        except Exception:
            pass
        return media_files[0].parent

    def _transcribe_parakeet_with_heartbeat(
        self,
        wav_file: Path,
        progress_callback: Optional[Callable[[str], None]],
        label: str
    ) -> str:
        """Run Parakeet transcription with periodic progress updates."""
        if not progress_callback:
            return self.parakeet.transcribe(wav_file)

        duration_seconds = self.converter.get_media_duration(wav_file) or 0.0
        if duration_seconds > 0:
            progress_callback(
                f"{label} Local transcription started ({duration_seconds / 60:.1f} min audio)..."
            )
        else:
            progress_callback(f"{label} Local transcription started...")

        stop_event = threading.Event()
        started_at = time.monotonic()

        def heartbeat():
            while not stop_event.wait(8):
                elapsed = int(time.monotonic() - started_at)
                try:
                    if duration_seconds > 0:
                        progress_callback(
                            f"{label} Still transcribing... {elapsed}s elapsed "
                            f"(audio {duration_seconds / 60:.1f} min)"
                        )
                    else:
                        progress_callback(f"{label} Still transcribing... {elapsed}s elapsed")
                except Exception:
                    # Don't let heartbeat errors interrupt transcription.
                    break

        heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
        heartbeat_thread.start()

        try:
            transcript = self.parakeet.transcribe(wav_file)
            elapsed = int(time.monotonic() - started_at)
            progress_callback(f"{label} ✓ Transcription complete in {elapsed}s")
            return transcript
        finally:
            stop_event.set()
            heartbeat_thread.join(timeout=1)

    def process_file(self,
                     media_file: Path,
                     output_base_dir: Optional[Path] = None,
                     progress_callback: Optional[Callable[[str], None]] = None) -> Path:
        """
        Process a single media file through the complete pipeline

        Args:
            media_file: Path to input media file
            output_base_dir: Base directory for output (defaults to same as input)
            progress_callback: Optional callback for progress updates

        Returns:
            Path to generated PDF file

        Raises:
            RuntimeError: If any step fails
        """
        if not self.is_supported_file(media_file):
            raise ValueError(f"Unsupported file type: {media_file.suffix}")

        if output_base_dir is None:
            output_base_dir = media_file.parent

        wav_file = None

        try:
            # Step 0: Extract file metadata
            if progress_callback:
                progress_callback(f"[0/4] Reading file metadata...")

            file_metadata = self.converter.get_media_metadata(media_file)

            # Step 1: Convert to WAV
            if progress_callback:
                progress_callback(f"[1/4] Converting {media_file.name}...")

            wav_file = self.converter.convert_to_wav(media_file, progress_callback)

            # Step 2: Transcribe with selected engine
            if progress_callback:
                engine_name = "Parakeet-MLX" if self.transcription_engine == TRANSCRIPTION_ENGINE_PARAKEET else "Whisper.cpp"
                progress_callback(f"[2/4] Transcribing with {engine_name}...")

            # Choose transcription engine
            if self.transcription_engine == TRANSCRIPTION_ENGINE_PARAKEET:
                raw_transcript = self._transcribe_parakeet_with_heartbeat(
                    wav_file,
                    progress_callback,
                    "[2/4]"
                )
            else:
                raw_transcript = self.whisper.transcribe(wav_file, progress_callback)

            # Step 3: Run formatting and metadata extraction IN PARALLEL (saves ~20-40% time)
            if progress_callback:
                # Determine formatter name
                if self.openai_formatting_model:
                    if "gpt-5-nano" in self.openai_formatting_model:
                        formatter_name = "GPT-5 nano"
                    elif "gpt-4o-mini" in self.openai_formatting_model:
                        formatter_name = "GPT-4o mini"
                    else:
                        formatter_name = "OpenAI"
                else:
                    formatter_name = "Claude Haiku 3.5"
                progress_callback(f"[3/4] Formatting with {formatter_name} + metadata extraction (parallel)...")

            # Storage for results from threads
            results = {}
            errors = {}

            def format_paragraphs():
                """Thread function for paragraph formatting"""
                try:
                    # Choose formatter based on preference
                    if self.openai_formatting_model:
                        formatter = OpenAIFormatter(model=self.openai_formatting_model)
                    else:
                        formatter = self.claude
                    results['formatted_transcript'] = formatter.format_into_paragraphs(
                        raw_transcript,
                        progress_callback=progress_callback
                    )
                except Exception as e:
                    errors['formatting'] = e

            def analyze_metadata():
                """Thread function for metadata analysis"""
                try:
                    # Choose metadata analyzer based on preference
                    if self.openai_metadata_model:
                        analyzer = OpenAIFormatter(model=self.openai_metadata_model)
                    else:
                        analyzer = self.claude
                    results['metadata'] = analyzer.analyze_transcript(
                        raw_transcript,
                        filename=media_file.name,
                        progress_callback=progress_callback
                    )
                except Exception as e:
                    errors['metadata'] = e

            # Start both threads simultaneously
            format_thread = threading.Thread(target=format_paragraphs)
            metadata_thread = threading.Thread(target=analyze_metadata)

            format_thread.start()
            metadata_thread.start()

            # Wait for both to complete
            format_thread.join()
            metadata_thread.join()

            # Check for errors
            if errors:
                error_msgs = ', '.join([f"{k}: {v}" for k, v in errors.items()])
                raise RuntimeError(f"Claude processing failed: {error_msgs}")

            # Extract results
            formatted_transcript = results['formatted_transcript']
            metadata = results['metadata']

            if progress_callback:
                progress_callback(f"✓ Parallel processing complete!")

            # Combine metadata with formatted transcript, file metadata, and engine info
            transcription_engine_name = "Parakeet-MLX" if self.transcription_engine == TRANSCRIPTION_ENGINE_PARAKEET else "Whisper AI"

            # Map model names to display names
            if self.openai_formatting_model:
                if "gpt-5-nano" in self.openai_formatting_model:
                    formatting_engine_name = "GPT-5 nano"
                elif "gpt-4o-mini" in self.openai_formatting_model:
                    formatting_engine_name = "GPT-4o mini"
                else:
                    formatting_engine_name = self.openai_formatting_model
            else:
                formatting_engine_name = "Claude Haiku 3.5"

            if self.openai_metadata_model:
                if "gpt-5-nano" in self.openai_metadata_model:
                    metadata_engine_name = "GPT-5 nano"
                elif "gpt-4o-mini" in self.openai_metadata_model:
                    metadata_engine_name = "GPT-4o mini"
                else:
                    metadata_engine_name = self.openai_metadata_model
            else:
                metadata_engine_name = "Claude Haiku 4.5"

            formatted_data = {
                **metadata,
                'formatted_transcript': formatted_transcript,
                'file_metadata': file_metadata,
                'engine_info': {
                    'transcription': transcription_engine_name,
                    'formatting': formatting_engine_name,
                    'metadata': metadata_engine_name
                }
            }

            # Step 4: Generate PDF
            if progress_callback:
                progress_callback(f"[4/4] Creating PDF file...")

            # Save in same folder as source file
            output_filename = self.pdf_gen.create_filename(
                media_file.name,
                formatted_data['speaker_name']
            )

            output_path = output_base_dir / output_filename

            # Create PDF file
            self.pdf_gen.create_pdf(formatted_data, output_path)

            if progress_callback:
                progress_callback(f"✓ Complete: {output_path.name}")
                progress_callback(f"  Saved to: {output_base_dir}")

            return output_path

        finally:
            # Cleanup temp WAV file
            if wav_file:
                self.converter.cleanup_temp_file(wav_file)

    def process_files_pipelined(self,
                                 media_files: list[Path],
                                 output_base_dir: Optional[Path] = None,
                                 progress_callback: Optional[Callable[[str], None]] = None) -> list[Path]:
        """
        Process multiple media files using a pipeline architecture.
        Whisper transcription and Claude formatting run in parallel on different files.

        Pipeline flow:
        File 1: Whisper -> Queue -> Claude
        File 2:            Whisper -> Queue -> Claude (while File 1 is in Claude)
        File 3:                       Whisper -> Queue -> Claude (while File 2 is in Claude)

        Args:
            media_files: List of media file paths
            output_base_dir: Base directory for output
            progress_callback: Optional callback for progress updates

        Returns:
            List of generated PDF file paths
        """
        results = []
        failures = []
        total = len(media_files)

        log_dir = output_base_dir if output_base_dir is not None else self._default_log_dir(media_files)
        log_file = log_dir / f"processing_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

        # Start log file
        log_lines = []
        log_lines.append("="*80)
        log_lines.append("TRANSCRIPT PROCESSOR - PIPELINED BATCH PROCESSING LOG")
        log_lines.append("="*80)
        log_lines.append(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log_lines.append(f"Total files: {total}")
        if output_base_dir is None:
            log_lines.append("Output directory: same folder as each source file")
        else:
            log_lines.append(f"Output directory: {output_base_dir}")
        log_lines.append(f"Log directory: {log_dir}")
        log_lines.append(f"Mode: PIPELINED (Whisper & Claude run in parallel)")
        log_lines.append("="*80)
        log_lines.append("")

        # Shared queue for passing work from Whisper to Claude
        work_queue = queue.Queue()

        # Thread-safe collections for results and failures
        results_lock = threading.Lock()
        log_lock = threading.Lock()

        def whisper_worker():
            """Worker that transcribes files and queues them for Claude"""
            for i, media_file in enumerate(media_files, 1):
                wav_file = None
                engine_name = "Parakeet" if self.transcription_engine == TRANSCRIPTION_ENGINE_PARAKEET else "Whisper"
                try:
                    if progress_callback:
                        progress_callback(f"[{engine_name} {i}/{total}] [0/4] Reading file metadata...")

                    # Extract file metadata
                    file_metadata = self.converter.get_media_metadata(media_file)

                    if progress_callback:
                        progress_callback(f"[{engine_name} {i}/{total}] [1/4] Converting {media_file.name}...")

                    # Convert to WAV
                    wav_file = self.converter.convert_to_wav(media_file, progress_callback)

                    if progress_callback:
                        progress_callback(f"[{engine_name} {i}/{total}] [2/4] Transcribing...")

                    # Transcribe with selected engine
                    if self.transcription_engine == TRANSCRIPTION_ENGINE_PARAKEET:
                        raw_transcript = self._transcribe_parakeet_with_heartbeat(
                            wav_file,
                            progress_callback,
                            f"[{engine_name} {i}/{total}]"
                        )
                    else:
                        raw_transcript = self.whisper.transcribe(wav_file, progress_callback)

                    if progress_callback:
                        progress_callback(f"[{engine_name} {i}/{total}] [2/4] ✓ Complete, queued for formatting")

                    # Put work in queue for Claude
                    work_queue.put({
                        'index': i,
                        'media_file': media_file,
                        'raw_transcript': raw_transcript,
                        'file_metadata': file_metadata,
                        'wav_file': wav_file,
                        'success': True
                    })

                except Exception as e:
                    # Put error in queue
                    work_queue.put({
                        'index': i,
                        'media_file': media_file,
                        'error': str(e),
                        'wav_file': wav_file,
                        'success': False
                    })

                    if progress_callback:
                        progress_callback(f"[{engine_name} {i}/{total}] ✗ Failed: {str(e)}")

            # Signal completion
            work_queue.put(None)

        def claude_worker():
            """Worker that processes transcripts with Claude"""
            processed = 0

            while True:
                # Get next item from queue
                item = work_queue.get()

                # None signals we're done
                if item is None:
                    work_queue.task_done()
                    break

                i = item['index']
                media_file = item['media_file']
                wav_file = item.get('wav_file')
                file_metadata = item.get('file_metadata', {})

                try:
                    if not item['success']:
                        # Whisper failed, log it
                        raise RuntimeError(item['error'])

                    raw_transcript = item['raw_transcript']

                    if progress_callback:
                        # Determine formatter name
                        if self.openai_formatting_model:
                            if "gpt-5-nano" in self.openai_formatting_model:
                                formatter_name = "GPT-5 nano"
                            elif "gpt-4o-mini" in self.openai_formatting_model:
                                formatter_name = "GPT-4o mini"
                            else:
                                formatter_name = "OpenAI"
                        else:
                            formatter_name = "Claude"
                        progress_callback(
                            f"[{formatter_name} {i}/{total}] [3/4] Formatting + metadata for {media_file.name}..."
                        )

                    # Run formatting and metadata IN PARALLEL (paragraph formatting + metadata)
                    claude_results = {}
                    claude_errors = {}

                    def format_paragraphs():
                        try:
                            # Choose formatter based on preference
                            if self.openai_formatting_model:
                                formatter = OpenAIFormatter(model=self.openai_formatting_model)
                            else:
                                formatter = self.claude
                            claude_results['formatted_transcript'] = formatter.format_into_paragraphs(
                                raw_transcript,
                                progress_callback=progress_callback
                            )
                        except Exception as e:
                            claude_errors['formatting'] = e

                    def analyze_metadata():
                        try:
                            # Choose metadata analyzer based on preference
                            if self.openai_metadata_model:
                                analyzer = OpenAIFormatter(model=self.openai_metadata_model)
                            else:
                                analyzer = self.claude
                            claude_results['metadata'] = analyzer.analyze_transcript(
                                raw_transcript,
                                filename=media_file.name,
                                progress_callback=progress_callback
                            )
                        except Exception as e:
                            claude_errors['metadata'] = e

                    # Start both threads simultaneously
                    format_thread = threading.Thread(target=format_paragraphs)
                    metadata_thread = threading.Thread(target=analyze_metadata)

                    format_thread.start()
                    metadata_thread.start()

                    format_thread.join()
                    metadata_thread.join()

                    # Check for errors
                    if claude_errors:
                        error_msgs = ', '.join([f"{k}: {v}" for k, v in claude_errors.items()])
                        raise RuntimeError(f"Claude processing failed: {error_msgs}")

                    # Extract results
                    formatted_transcript = claude_results['formatted_transcript']
                    metadata = claude_results['metadata']

                    # Combine data with engine info
                    transcription_engine_name = "Parakeet-MLX" if self.transcription_engine == TRANSCRIPTION_ENGINE_PARAKEET else "Whisper AI"

                    # Map model names to display names
                    if self.openai_formatting_model:
                        if "gpt-5-nano" in self.openai_formatting_model:
                            formatting_engine_name = "GPT-5 nano"
                        elif "gpt-4o-mini" in self.openai_formatting_model:
                            formatting_engine_name = "GPT-4o mini"
                        else:
                            formatting_engine_name = self.openai_formatting_model
                    else:
                        formatting_engine_name = "Claude Haiku 3.5"

                    if self.openai_metadata_model:
                        if "gpt-5-nano" in self.openai_metadata_model:
                            metadata_engine_name = "GPT-5 nano"
                        elif "gpt-4o-mini" in self.openai_metadata_model:
                            metadata_engine_name = "GPT-4o mini"
                        else:
                            metadata_engine_name = self.openai_metadata_model
                    else:
                        metadata_engine_name = "Claude Haiku 4.5"

                    formatted_data = {
                        **metadata,
                        'formatted_transcript': formatted_transcript,
                        'file_metadata': file_metadata,
                        'engine_info': {
                            'transcription': transcription_engine_name,
                            'formatting': formatting_engine_name,
                            'metadata': metadata_engine_name
                        }
                    }

                    # Generate PDF
                    if progress_callback:
                        progress_callback(f"[Claude {i}/{total}] [4/4] Creating PDF...")

                    output_filename = self.pdf_gen.create_filename(
                        media_file.name,
                        formatted_data['speaker_name']
                    )

                    target_output_dir = output_base_dir if output_base_dir is not None else media_file.parent
                    output_path = target_output_dir / output_filename
                    self.pdf_gen.create_pdf(formatted_data, output_path)

                    if progress_callback:
                        progress_callback(f"[Claude {i}/{total}] ✓ Complete: {output_path.name}")

                    # Store result
                    with results_lock:
                        results.append(output_path)

                    # Log success
                    with log_lock:
                        log_lines.append(f"[{i}/{total}] {media_file.name}")
                        log_lines.append(f"  ✓ SUCCESS: {output_path.name}")
                        log_lines.append("")

                except Exception as e:
                    error_msg = f"✗ Failed to process {media_file.name}: {str(e)}"
                    if progress_callback:
                        progress_callback(f"[Claude {i}/{total}] {error_msg}")

                    # Store failure
                    with results_lock:
                        failures.append({
                            'file': media_file.name,
                            'error': str(e)
                        })

                    # Log failure
                    with log_lock:
                        log_lines.append(f"[{i}/{total}] {media_file.name}")
                        log_lines.append(f"  ✗ FAILED: {str(e)}")
                        log_lines.append("")

                finally:
                    # Cleanup temp WAV file
                    if wav_file:
                        self.converter.cleanup_temp_file(wav_file)

                    processed += 1

                work_queue.task_done()

        # Start worker threads
        whisper_thread = threading.Thread(target=whisper_worker, daemon=True)
        claude_thread = threading.Thread(target=claude_worker, daemon=True)

        whisper_thread.start()
        claude_thread.start()

        # Wait for completion
        whisper_thread.join()
        claude_thread.join()
        work_queue.join()

        # Write summary
        log_lines.append("="*80)
        log_lines.append("SUMMARY")
        log_lines.append("="*80)
        log_lines.append(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log_lines.append(f"Successful: {len(results)}/{total}")
        log_lines.append(f"Failed: {len(failures)}/{total}")
        log_lines.append("")

        if failures:
            log_lines.append("FAILED FILES:")
            log_lines.append("-"*80)
            for failure in failures:
                log_lines.append(f"  • {failure['file']}")
                log_lines.append(f"    Error: {failure['error']}")
                log_lines.append("")

        log_lines.append("="*80)

        # Write log file
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(log_lines))
            if progress_callback:
                progress_callback(f"📋 Log saved: {log_file}")
        except Exception as e:
            if progress_callback:
                progress_callback(f"⚠️ Warning: Could not write log file: {e}")

        if progress_callback:
            progress_callback(f"\n{'='*60}")
            progress_callback(f"Completed: {len(results)}/{total} files processed successfully")
            if failures:
                progress_callback(f"⚠️  {len(failures)} files failed - see log for details")
            progress_callback(f"{'='*60}")

        return results

    def process_files(self,
                      media_files: list[Path],
                      output_base_dir: Optional[Path] = None,
                      progress_callback: Optional[Callable[[str], None]] = None) -> list[Path]:
        """
        Process multiple media files

        Args:
            media_files: List of media file paths
            output_base_dir: Base directory for output
            progress_callback: Optional callback for progress updates

        Returns:
            List of generated PDF file paths
        """
        results = []
        failures = []
        total = len(media_files)

        log_dir = output_base_dir if output_base_dir is not None else self._default_log_dir(media_files)
        log_file = log_dir / f"processing_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

        # Start log file
        log_lines = []
        log_lines.append("="*80)
        log_lines.append("TRANSCRIPT PROCESSOR - BATCH PROCESSING LOG")
        log_lines.append("="*80)
        log_lines.append(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log_lines.append(f"Total files: {total}")
        if output_base_dir is None:
            log_lines.append("Output directory: same folder as each source file")
        else:
            log_lines.append(f"Output directory: {output_base_dir}")
        log_lines.append(f"Log directory: {log_dir}")
        log_lines.append("="*80)
        log_lines.append("")

        for i, media_file in enumerate(media_files, 1):
            try:
                if progress_callback:
                    progress_callback(f"\n{'='*60}")
                    progress_callback(f"Processing file {i}/{total}: {media_file.name}")
                    progress_callback(f"{'='*60}")

                log_lines.append(f"[{i}/{total}] {media_file.name}")

                output_path = self.process_file(
                    media_file,
                    output_base_dir,
                    progress_callback
                )
                results.append(output_path)

                # Log success
                log_lines.append(f"  ✓ SUCCESS: {output_path.name}")
                log_lines.append("")

            except Exception as e:
                error_msg = f"✗ Failed to process {media_file.name}: {str(e)}"
                if progress_callback:
                    progress_callback(error_msg)

                # Log failure
                failures.append({
                    'file': media_file.name,
                    'error': str(e)
                })
                log_lines.append(f"  ✗ FAILED: {str(e)}")
                log_lines.append("")

                # Continue with next file
                continue

        # Write summary
        log_lines.append("="*80)
        log_lines.append("SUMMARY")
        log_lines.append("="*80)
        log_lines.append(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log_lines.append(f"Successful: {len(results)}/{total}")
        log_lines.append(f"Failed: {len(failures)}/{total}")
        log_lines.append("")

        if failures:
            log_lines.append("FAILED FILES:")
            log_lines.append("-"*80)
            for failure in failures:
                log_lines.append(f"  • {failure['file']}")
                log_lines.append(f"    Error: {failure['error']}")
                log_lines.append("")

        log_lines.append("="*80)

        # Write log file
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(log_lines))

        if progress_callback:
            progress_callback(f"\n{'='*60}")
            progress_callback(f"Completed: {len(results)}/{total} files processed successfully")
            if failures:
                progress_callback(f"⚠️  {len(failures)} files failed - see log for details")
            progress_callback(f"📋 Log file: {log_file.name}")
            progress_callback(f"{'='*60}")

        return results
