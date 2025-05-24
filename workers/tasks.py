# Celery tasks
import os
import subprocess
import logging
from .celery_app import celery_app
from app.models.media import Media
from app.core.config import settings # To get DATABASE_URL
from sqlmodel import create_engine, Session

# Setup logging
logger = logging.getLogger(__name__)

# Define a directory for extracted audio files
AUDIO_EXTRACTED_DIRECTORY = "audio_extracted"

# Create a global engine instance for tasks (Celery workers are separate processes)
# This should ideally use the same DB URL as the main app.
engine = create_engine(settings.DATABASE_URL, echo=False) # Set echo=False for less verbose logs in worker


@celery_app.task(name="extract_audio_task")
def extract_audio_task(media_id: int) -> str:
    """
    Celery task to extract audio from a video file using ffmpeg.
    Updates the Media record with the path to the extracted audio file.
    """
    logger.info(f"Starting audio extraction for media_id: {media_id}")
    os.makedirs(AUDIO_EXTRACTED_DIRECTORY, exist_ok=True)

    # Create a new database session for this task
    with Session(engine) as session:
        try:
            media_record = session.get(Media, media_id)
            if not media_record:
                logger.error(f"Media record with id {media_id} not found.")
                return f"Error: Media record {media_id} not found."

            if not media_record.source_path or not os.path.exists(media_record.source_path):
                logger.error(f"Source video file not found for media_id {media_id} at path: {media_record.source_path}")
                return f"Error: Source video file not found for media_id {media_id}."

            video_path = media_record.source_path
            base_filename = os.path.splitext(os.path.basename(video_path))[0]
            audio_filename = f"{base_filename}.wav" # Using .wav for potentially better quality for Whisper
            audio_path = os.path.join(AUDIO_EXTRACTED_DIRECTORY, audio_filename)

            # Ensure the output directory for this specific audio file exists (it should due to the earlier makedirs)
            # os.makedirs(os.path.dirname(audio_path), exist_ok=True) # Redundant if AUDIO_EXTRACTED_DIRECTORY is flat

            # ffmpeg command to extract audio as WAV
            # -vn: disable video recording
            # -acodec pcm_s16le: WAV format (16-bit PCM)
            # -ar 44100: sample rate 44.1kHz
            # -ac 2: stereo audio
            # -y: overwrite output file if it exists
            ffmpeg_command = [
                "ffmpeg",
                "-i", video_path,
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", "44100",
                "-ac", "2",
                "-y", # Overwrite output file without asking
                audio_path,
            ]

            logger.info(f"Executing ffmpeg command: {' '.join(ffmpeg_command)}")
            process = subprocess.run(ffmpeg_command, capture_output=True, text=True, check=False)

            if process.returncode == 0:
                media_record.audio_path = audio_path
                session.add(media_record)
                session.commit()
                session.refresh(media_record)
                logger.info(f"Audio successfully extracted for media_id {media_id}. Audio saved at: {audio_path}")
                
                # Chain the transcription task
                try:
                    logger.info(f"Queueing transcription task for media_id: {media_id}")
                    transcribe_audio_task.delay(media_id) # Call the new task
                except Exception as e_chain:
                    logger.error(f"Failed to queue transcription task for media_id {media_id}: {str(e_chain)}")
                    # Depending on requirements, you might want to mark the media record
                    # as "audio_extracted_transcription_failed_to_queue" or similar

                return f"Audio extracted successfully: {audio_path}"
            else:
                logger.error(f"ffmpeg command failed for media_id {media_id}. Error: {process.stderr}")
                return f"Error extracting audio for media_id {media_id}: {process.stderr}"

        except Exception as e:
            logger.exception(f"An unexpected error occurred in extract_audio_task for media_id {media_id}: {e}")
            # session.rollback() # Rollback in case of error, though with check=False for subprocess, this might be complex
            return f"Unexpected error in extract_audio_task for media_id {media_id}: {str(e)}"


TRANSCRIPTION_DIRECTORY = "transcriptions"
# Attempt to load Whisper model globally to potentially save time on subsequent tasks.
# This might consume more memory in the worker process from the start.
# If this causes issues (e.g. OOM in constrained environments), move model loading inside the task.
WHISPER_MODEL = None
try:
    import whisper
    WHISPER_MODEL = whisper.load_model("base") # Load "base" model by default
    logger.info("Whisper model 'base' loaded globally in worker.")
except Exception as e:
    logger.error(f"Failed to load Whisper model globally: {e}")
    WHISPER_MODEL = None


@celery_app.task(name="transcribe_audio_task")
def transcribe_audio_task(media_id: int) -> str:
    """
    Celery task to transcribe an audio file using Whisper.
    Updates the Media record with the path to the transcription file.
    """
    global WHISPER_MODEL # Allow modification if model loading is deferred/retried
    logger.info(f"Starting transcription for media_id: {media_id}")
    os.makedirs(TRANSCRIPTION_DIRECTORY, exist_ok=True)

    with Session(engine) as session:
        try:
            media_record = session.get(Media, media_id)
            if not media_record:
                logger.error(f"Transcription: Media record with id {media_id} not found.")
                return f"Error: Media record {media_id} not found for transcription."

            if not media_record.audio_path or not os.path.exists(media_record.audio_path):
                logger.error(f"Transcription: Audio file not found for media_id {media_id} at path: {media_record.audio_path}")
                return f"Error: Audio file not found for media_id {media_id} for transcription."

            if WHISPER_MODEL is None:
                # Attempt to load model if global loading failed or if it's the first time.
                try:
                    import whisper
                    WHISPER_MODEL = whisper.load_model("base") # Or "small", "medium" etc.
                    logger.info("Whisper model 'base' loaded within transcribe_audio_task.")
                except Exception as e_load:
                    logger.error(f"Failed to load Whisper model within task: {e_load}")
                    return f"Error: Could not load Whisper model for media_id {media_id}."
            
            audio_path = media_record.audio_path
            # Use media_id for transcription filename to ensure uniqueness and easy lookup
            transcription_filename = f"{media_record.id}_transcription.json"
            transcription_path = os.path.join(TRANSCRIPTION_DIRECTORY, transcription_filename)

            logger.info(f"Transcribing audio file: {audio_path} for media_id: {media_id}")
            
            # Perform transcription with word timestamps
            # Ensure the language matches the media_record.language if Whisper supports it
            # For now, auto-detect or assume English if not specified.
            # Add `language=media_record.language` to transcribe options if language is known and supported by Whisper.
            transcription_result = WHISPER_MODEL.transcribe(audio_path, word_timestamps=True, language=media_record.language if media_record.language else None)
            
            # Save the detailed transcription result as JSON
            import json
            with open(transcription_path, "w", encoding="utf-8") as f:
                json.dump(transcription_result, f, ensure_ascii=False, indent=4)

            media_record.transcription_path = transcription_path
            session.add(media_record)
            session.commit()
            session.refresh(media_record)
            
            logger.info(f"Transcription successful for media_id {media_id}. Saved to: {transcription_path}")

            # Chain the segmentation and tokenization task
            try:
                logger.info(f"Queueing segmentation and tokenization task for media_id: {media_id}")
                segment_and_tokenize_task.delay(media_id) # Call the new task
            except Exception as e_chain:
                logger.error(f"Failed to queue segmentation and tokenization task for media_id {media_id}: {str(e_chain)}")

            return f"Transcription successful for media_id {media_id}: {transcription_path}"

        except Exception as e:
            logger.exception(f"An unexpected error occurred in transcribe_audio_task for media_id {media_id}: {e}")
            # session.rollback() # Good practice if complex operations before commit
            return f"Unexpected error in transcribe_audio_task for media_id {media_id}: {str(e)}"


CUE_MAX_DURATION_MS = 8000  # 8 seconds

@celery_app.task(name="segment_and_tokenize_task")
def segment_and_tokenize_task(media_id: int) -> str:
    logger.info(f"Starting segmentation and tokenization for media_id: {media_id}")

    with Session(engine) as session:
        try:
            media_record = session.get(Media, media_id)
            if not media_record:
                logger.error(f"S&T: Media record {media_id} not found.")
                return f"Error: Media record {media_id} not found."

            if not media_record.transcription_path or not os.path.exists(media_record.transcription_path):
                logger.error(f"S&T: Transcription file not found for media_id {media_id} at {media_record.transcription_path}")
                return f"Error: Transcription file not found for media_id {media_id}."

            if not media_record.language:
                logger.error(f"S&T: Language not set for media_id {media_id}.")
                return f"Error: Language not set for media_id {media_id}."

            # Load transcription data
            import json
            with open(media_record.transcription_path, "r", encoding="utf-8") as f:
                transcription_data = json.load(f)

            # Instantiate language plugin (Hardcoded for Japanese for now)
            lang_plugin = None
            if media_record.language.lower() == "ja" or media_record.language.lower() == "jpn":
                from language_plugins.japanese.plugin import JapanesePlugin
                plugin_instance = JapanesePlugin()
                if not plugin_instance.tokenizer:
                     logger.error(f"S&T: Failed to initialize JapanesePlugin for media_id {media_id}.")
                     return f"Error: Failed to initialize JapanesePlugin for media_id {media_id}."
                lang_plugin = plugin_instance
            else:
                logger.warning(f"S&T: No language plugin for '{media_record.language}' for media_id {media_id}. Skipping tokenization part.")
                # For now, we will not create cues if we can't tokenize. 
                # Alternatively, create cues without token-specific markdown.
                return f"Warning: No plugin for language {media_record.language}. Cues not created."


            all_words_from_transcription = []
            for segment in transcription_data.get("segments", []):
                for word_info in segment.get("words", []): # Whisper word structure
                    # Ensure word_info is a dict and has 'word', 'start', 'end'
                    if isinstance(word_info, dict) and 'word' in word_info and 'start' in word_info and 'end' in word_info:
                         all_words_from_transcription.append({
                            "text": word_info["word"],
                            "start_ms": int(word_info["start"] * 1000),
                            "end_ms": int(word_info["end"] * 1000),
                        })
                    else:
                        logger.warning(f"S&T: Skipping invalid word data in segment for media_id {media_id}: {word_info}")
            
            if not all_words_from_transcription:
                logger.info(f"S&T: No words found in transcription for media_id {media_id}. Nothing to segment.")
                return f"No words to segment for media_id {media_id}."

            # Segment cues
            current_cue_words = []
            current_cue_text = ""
            current_cue_start_ms = all_words_from_transcription[0]["start_ms"]
            cue_count = 0

            for i, word_data in enumerate(all_words_from_transcription):
                word_text = word_data["text"]
                word_start_ms = word_data["start_ms"]
                word_end_ms = word_data["end_ms"]

                if not current_cue_words: # First word of a new cue
                    current_cue_start_ms = word_start_ms
                
                potential_cue_duration = word_end_ms - current_cue_start_ms

                if current_cue_words and potential_cue_duration > CUE_MAX_DURATION_MS:
                    # Finalize current cue
                    from app.models.subtitle import SubtitleCue, Word # Ensure models are imported
                    
                    # Tokenize and build markdown
                    markdown_parts = []
                    if lang_plugin:
                        tokens = lang_plugin.tokenize(current_cue_text.strip())
                        for token in tokens:
                            surface = token['surface']
                            lemma = token['lemma']
                            
                            # Get or create Word
                            db_word = session.exec(
                                select(Word).where(Word.lemma == lemma, Word.language == media_record.language)
                            ).first()
                            if not db_word:
                                db_word = Word(lemma=lemma, language=media_record.language)
                                session.add(db_word)
                                session.flush() # To get db_word.id
                            
                            markdown_parts.append(f'<span class="w-0" data-wid="{db_word.id}">{surface}</span>')
                    else: # No plugin, just append text
                        markdown_parts.append(current_cue_text.strip())
                        
                    final_text_markdown = "".join(markdown_parts)
                    
                    new_cue = SubtitleCue(
                        media_id=media_id,
                        start_ms=current_cue_start_ms,
                        end_ms=current_cue_words[-1]["end_ms"], # end time of last word in this cue
                        text_markdown=final_text_markdown
                    )
                    session.add(new_cue)
                    cue_count += 1
                    
                    # Reset for next cue
                    current_cue_words = []
                    current_cue_text = ""
                    current_cue_start_ms = word_start_ms # Current word starts the new cue

                # Add current word to current cue
                current_cue_words.append(word_data)
                current_cue_text += word_text # Adding space implicitly handled by Whisper word text (often includes leading/trailing space)

            # Add the last cue
            if current_cue_words:
                from app.models.subtitle import SubtitleCue, Word
                markdown_parts = []
                if lang_plugin:
                    tokens = lang_plugin.tokenize(current_cue_text.strip())
                    for token in tokens:
                        surface = token['surface']
                        lemma = token['lemma']
                        db_word = session.exec(
                            select(Word).where(Word.lemma == lemma, Word.language == media_record.language)
                        ).first()
                        if not db_word:
                            db_word = Word(lemma=lemma, language=media_record.language)
                            session.add(db_word)
                            session.flush()
                        markdown_parts.append(f'<span class="w-0" data-wid="{db_word.id}">{surface}</span>')
                else:
                     markdown_parts.append(current_cue_text.strip())
                final_text_markdown = "".join(markdown_parts)

                new_cue = SubtitleCue(
                    media_id=media_id,
                    start_ms=current_cue_start_ms,
                    end_ms=current_cue_words[-1]["end_ms"],
                    text_markdown=final_text_markdown
                )
                session.add(new_cue)
                cue_count +=1

            session.commit()
            logger.info(f"S&T: Successfully created {cue_count} subtitle cues for media_id {media_id}.")
            return f"Successfully created {cue_count} subtitle cues for media_id {media_id}."

        except Exception as e:
            logger.info(f"S&T: Successfully created {cue_count} subtitle cues for media_id {media_id}.")
            
            # Chain the WebVTT generation task
            try:
                logger.info(f"S&T: Queueing WebVTT generation task for media_id: {media_id}")
                generate_webvtt_task.delay(media_id)
            except Exception as e_chain:
                logger.error(f"S&T: Failed to queue WebVTT generation task for media_id {media_id}: {str(e_chain)}")

            return f"Successfully created {cue_count} subtitle cues for media_id {media_id}."

        except Exception as e:
            logger.exception(f"S&T: An unexpected error occurred for media_id {media_id}: {e}")
            session.rollback()
            return f"S&T: Unexpected error for media_id {media_id}: {str(e)}"


WEBVTT_DIRECTORY = "webvtt_files"

def format_ms_to_webvtt_timestamp(ms: int) -> str:
    """Converts milliseconds to HH:MM:SS.mmm format for WebVTT."""
    seconds, milliseconds = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

@celery_app.task(name="generate_webvtt_task")
def generate_webvtt_task(media_id: int) -> str:
    logger.info(f"WebVTT Gen: Starting WebVTT generation for media_id: {media_id}")
    os.makedirs(WEBVTT_DIRECTORY, exist_ok=True)

    with Session(engine) as session:
        try:
            media_record = session.get(Media, media_id)
            if not media_record:
                logger.error(f"WebVTT Gen: Media record {media_id} not found.")
                return f"Error: Media record {media_id} not found for WebVTT generation."

            from app.models.subtitle import SubtitleCue # Ensure SubtitleCue is imported
            from sqlmodel import select

            statement = select(SubtitleCue).where(SubtitleCue.media_id == media_id).order_by(SubtitleCue.start_ms)
            cues = session.exec(statement).all()

            if not cues:
                logger.info(f"WebVTT Gen: No subtitle cues found for media_id {media_id}. WebVTT file will be empty except header.")
                # Optionally, still create an empty VTT or skip file creation
            
            vtt_content_parts = ["WEBVTT\n"]
            for cue in cues:
                start_time = format_ms_to_webvtt_timestamp(cue.start_ms)
                end_time = format_ms_to_webvtt_timestamp(cue.end_ms)
                vtt_content_parts.append(f"{start_time} --> {end_time}\n{cue.text_markdown}\n")
            
            full_vtt_content = "\n".join(vtt_content_parts)

            # Basic slugification for filename from title
            slug_title = "".join(c if c.isalnum() else "_" for c in media_record.title).strip("_")
            if not slug_title: slug_title = "untitled" # Handle empty titles
            vtt_filename = f"{media_record.id}_{slug_title[:50]}.vtt" # Max 50 chars for slug part
            vtt_path = os.path.join(WEBVTT_DIRECTORY, vtt_filename)

            with open(vtt_path, "w", encoding="utf-8") as f:
                f.write(full_vtt_content)
            
            media_record.webvtt_path = vtt_path
            session.add(media_record)
            session.commit()
            session.refresh(media_record)

            logger.info(f"WebVTT Gen: Successfully generated WebVTT file for media_id {media_id} at {vtt_path}")
            return f"WebVTT file generated for media_id {media_id}: {vtt_path}"

        except Exception as e:
            logger.exception(f"WebVTT Gen: An unexpected error occurred for media_id {media_id}: {e}")
            session.rollback() # Rollback on error
            return f"WebVTT Gen: Unexpected error for media_id {media_id}: {str(e)}"


# Keep existing tasks (or remove if they are not part of this specific feature set)
@celery_app.task(name="process_subtitle")
def process_subtitle(subtitle_id: int, language: str):
    print(f"Processing subtitle ID: {subtitle_id} for language: {language}")
    return f"Subtitle {subtitle_id} processing initiated for {language}."

@celery_app.task(name="nlp_process_word")
def nlp_process_word(word_id: int, language: str):
    print(f"NLP processing for word ID: {word_id} in language: {language}")
    return f"NLP processing for word {word_id} ({language}) initiated."
