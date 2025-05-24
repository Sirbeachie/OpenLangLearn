# Celery tasks
import os
import subprocess
import logging
import tempfile # For creating temporary directories/files
import shutil # For cleaning up directories
import json # For transcription data handling

from .celery_app import celery_app
from app.models.media import Media
from app.models.subtitle import SubtitleCue, Word # SubtitleCue and Word models
from app.core.config import settings # Centralized settings
from app.core.s3_client import get_s3_client, upload_file_to_s3, download_file_from_s3 # S3 utilities
from sqlmodel import create_engine, Session, select

# Import exceptions for retries
from botocore.exceptions import ClientError
from sqlalchemy.exc import OperationalError

# Import for dynamic language plugin loading
from language_plugins.registry import get_language_plugin

# Setup logging
logger = logging.getLogger(__name__)

# S3 prefixes are operational constants for key structure, not user-configurable paths.
S3_AUDIO_PREFIX = "audio_extracted"
S3_TRANSCRIPTION_PREFIX = "transcriptions"
S3_WEBVTT_PREFIX = "webvtt_files"

engine = create_engine(settings.DATABASE_URL, echo=False) 
WHISPER_MODEL = None

@celery_app.on_after_configure.connect
def load_whisper_model(sender, **kwargs):
    global WHISPER_MODEL
    if settings.S3_BUCKET_NAME and settings.WHISPER_MODEL_NAME: 
        try:
            import whisper
            logger.info(f"Attempting to load Whisper model: {settings.WHISPER_MODEL_NAME}")
            WHISPER_MODEL = whisper.load_model(settings.WHISPER_MODEL_NAME) 
            logger.info(f"Whisper model '{settings.WHISPER_MODEL_NAME}' loaded successfully in Celery worker.")
        except Exception as e:
            logger.error(f"Failed to load Whisper model '{settings.WHISPER_MODEL_NAME}' in Celery worker: {e}")
    else:
        if not settings.S3_BUCKET_NAME: logger.info("S3_BUCKET_NAME not set, Whisper model loading skipped.")
        if not settings.WHISPER_MODEL_NAME: logger.info("WHISPER_MODEL_NAME not set, Whisper model loading skipped.")


@celery_app.task(bind=True, autoretry_for=(ClientError, OperationalError), retry_kwargs={'max_retries': 3, 'countdown': 60})
def extract_audio_task(self, media_id: int) -> str:
    task_id = self.request.id
    logger.info(f"AudioExt(TaskID:{task_id}): Starting for media_id: {media_id}. Attempt: {self.request.retries + 1}")
    s3_client = get_s3_client()
    if not s3_client:
        logger.error(f"AudioExt(TaskID:{task_id}): S3 client unavailable for media_id {media_id}. Cannot proceed.")
        return f"AudioExt: Error - S3 client not available for media_id {media_id}."

    task_temp_dir = tempfile.mkdtemp(dir=settings.TASK_TEMP_BASE_DIR)
    
    try:
        with Session(engine) as session:
            media_record = session.get(Media, media_id)
            if not media_record:
                logger.error(f"AudioExt(TaskID:{task_id}): Media record {media_id} not found.")
                return f"AudioExt: Error - Media record {media_id} not found."
            if not media_record.source_path: 
                logger.error(f"AudioExt(TaskID:{task_id}): Source S3 key missing for media_id {media_id}.")
                return f"AudioExt: Error - Source S3 key missing for media_id {media_id}."

            video_s3_key = media_record.source_path
            original_extension = os.path.splitext(os.path.basename(video_s3_key))[1]
            local_video_filename = f"{media_id}_source{original_extension}"
            local_video_path = os.path.join(task_temp_dir, local_video_filename)

            logger.info(f"AudioExt(TaskID:{task_id}): Downloading {video_s3_key} to {local_video_path} for media_id {media_id}")
            if not download_file_from_s3(settings.S3_BUCKET_NAME, video_s3_key, local_video_path, s3_client):
                logger.error(f"AudioExt(TaskID:{task_id}): Failed to download video from S3 for media_id {media_id}.")
                raise Exception(f"S3 download failed for {video_s3_key}")


            local_audio_filename = f"{media_id}_extracted_audio.wav"
            local_audio_path = os.path.join(task_temp_dir, local_audio_filename)
            
            logger.info(f"AudioExt(TaskID:{task_id}): Preparing ffmpeg command for media_id {media_id}")
            ffmpeg_command = [
                "ffmpeg", "-i", local_video_path,
                "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
                "-y", local_audio_path,
            ]
            logger.info(f"AudioExt(TaskID:{task_id}): Executing ffmpeg for media_id {media_id}: {' '.join(ffmpeg_command)}")
            process = subprocess.run(ffmpeg_command, capture_output=True, text=True, check=False)

            if process.returncode == 0:
                logger.info(f"AudioExt(TaskID:{task_id}): ffmpeg successful for media_id {media_id}.")
                audio_s3_key = f"{S3_AUDIO_PREFIX}/{media_id}/{local_audio_filename}"
                logger.info(f"AudioExt(TaskID:{task_id}): Uploading {local_audio_path} to S3 as {audio_s3_key} for media_id {media_id}")
                if not upload_file_to_s3(local_audio_path, settings.S3_BUCKET_NAME, audio_s3_key, s3_client):
                    logger.error(f"AudioExt(TaskID:{task_id}): Failed to upload audio to S3 for media_id {media_id}.")
                    raise Exception(f"S3 upload failed for {audio_s3_key}")


                media_record.audio_path = audio_s3_key
                session.add(media_record)
                session.commit()
                session.refresh(media_record)
                logger.info(f"AudioExt(TaskID:{task_id}): Audio S3 key {audio_s3_key} saved for media_id {media_id}.")
                
                transcribe_audio_task.delay(media_id)
                return f"AudioExt(TaskID:{task_id}): Success for media_id {media_id}: {audio_s3_key}"
            else:
                logger.error(f"AudioExt(TaskID:{task_id}): ffmpeg failed for media_id {media_id}. Return code: {process.returncode}. Error: {process.stderr}")
                return f"AudioExt: Error - ffmpeg failed for media_id {media_id}: {process.stderr}"
    except (ClientError, OperationalError) as exc: 
        logger.warning(f"AudioExt(TaskID:{task_id}): Retrying for media_id {media_id} due to {type(exc).__name__}: {exc}. Attempt: {self.request.retries + 1}")
        raise 
    except Exception as e:
        logger.exception(f"AudioExt(TaskID:{task_id}): Unexpected error for media_id {media_id}: {e}")
        return f"AudioExt(TaskID:{task_id}): Unexpected error for media_id {media_id}: {str(e)}"
    finally:
        if os.path.exists(task_temp_dir):
            shutil.rmtree(task_temp_dir)
            logger.info(f"AudioExt(TaskID:{task_id}): Cleaned temp dir {task_temp_dir} for media_id {media_id}")


@celery_app.task(bind=True, autoretry_for=(ClientError, OperationalError), retry_kwargs={'max_retries': 3, 'countdown': 60})
def transcribe_audio_task(self, media_id: int) -> str:
    task_id = self.request.id
    logger.info(f"Transcribe(TaskID:{task_id}): Starting for media_id: {media_id}. Attempt: {self.request.retries + 1}")
    global WHISPER_MODEL
    s3_client = get_s3_client()
    if not s3_client: 
        logger.error(f"Transcribe(TaskID:{task_id}): S3 client unavailable for media_id {media_id}. Cannot proceed.")
        return f"Transcribe: Error - S3 client unavailable for media_id {media_id}."
    if WHISPER_MODEL is None: 
        logger.error(f"Transcribe(TaskID:{task_id}): Whisper model '{settings.WHISPER_MODEL_NAME}' not loaded. Cannot process media_id {media_id}.")
        return f"Transcribe: Error - Whisper model '{settings.WHISPER_MODEL_NAME}' not loaded for media_id {media_id}."

    task_temp_dir = tempfile.mkdtemp(dir=settings.TASK_TEMP_BASE_DIR)
    try:
        with Session(engine) as session:
            media_record = session.get(Media, media_id)
            if not media_record: 
                logger.error(f"Transcribe(TaskID:{task_id}): Media record {media_id} not found.")
                return f"Transcribe: Error - Media record {media_id} not found."
            if not media_record.audio_path: 
                logger.error(f"Transcribe(TaskID:{task_id}): Audio S3 key missing for media_id {media_id}.")
                return f"Transcribe: Error - Audio S3 key missing for media_id {media_id}."

            audio_s3_key = media_record.audio_path
            local_audio_filename = f"{media_id}_downloaded_audio.wav"
            local_audio_path = os.path.join(task_temp_dir, local_audio_filename)

            logger.info(f"Transcribe(TaskID:{task_id}): Downloading {audio_s3_key} to {local_audio_path} for media_id {media_id}")
            if not download_file_from_s3(settings.S3_BUCKET_NAME, audio_s3_key, local_audio_path, s3_client):
                logger.error(f"Transcribe(TaskID:{task_id}): Failed to download audio from S3 for media_id {media_id}.")
                raise Exception(f"S3 download failed for {audio_s3_key}")
            
            transcription_language = media_record.language if media_record.language else settings.DEFAULT_PROCESSING_LANGUAGE
            logger.info(f"Transcribe(TaskID:{task_id}): Performing transcription for {local_audio_path} (media_id: {media_id}, lang: {transcription_language or 'auto'})")
            
            transcription_result = WHISPER_MODEL.transcribe(
                local_audio_path, word_timestamps=True, 
                language=transcription_language
            )
            
            local_transcription_filename = f"{media_id}_transcription.json"
            local_transcription_path = os.path.join(task_temp_dir, local_transcription_filename)
            logger.info(f"Transcribe(TaskID:{task_id}): Saving transcription locally to {local_transcription_path} for media_id {media_id}")
            with open(local_transcription_path, "w", encoding="utf-8") as f:
                json.dump(transcription_result, f, ensure_ascii=False, indent=4)

            transcription_s3_key = f"{S3_TRANSCRIPTION_PREFIX}/{media_id}/{local_transcription_filename}"
            logger.info(f"Transcribe(TaskID:{task_id}): Uploading {local_transcription_path} to S3 as {transcription_s3_key} for media_id {media_id}")
            if not upload_file_to_s3(local_transcription_path, settings.S3_BUCKET_NAME, transcription_s3_key, s3_client):
                logger.error(f"Transcribe(TaskID:{task_id}): Failed to upload transcription to S3 for media_id {media_id}.")
                raise Exception(f"S3 upload failed for {transcription_s3_key}")


            media_record.transcription_path = transcription_s3_key
            session.add(media_record)
            session.commit()
            session.refresh(media_record)
            logger.info(f"Transcribe(TaskID:{task_id}): S3 key {transcription_s3_key} saved for media_id {media_id}.")
            
            segment_and_tokenize_task.delay(media_id)
            return f"Transcribe(TaskID:{task_id}): Success for media_id {media_id}: {transcription_s3_key}"
    except (ClientError, OperationalError) as exc:
        logger.warning(f"Transcribe(TaskID:{task_id}): Retrying for media_id {media_id} due to {type(exc).__name__}: {exc}. Attempt: {self.request.retries + 1}")
        raise
    except Exception as e:
        logger.exception(f"Transcribe(TaskID:{task_id}): Unexpected error for media_id {media_id}: {e}")
        return f"Transcribe(TaskID:{task_id}): Unexpected error for media_id {media_id}: {str(e)}"
    finally:
        if os.path.exists(task_temp_dir):
            shutil.rmtree(task_temp_dir)
            logger.info(f"Transcribe(TaskID:{task_id}): Cleaned temp dir {task_temp_dir} for media_id {media_id}")


CUE_MAX_DURATION_MS = 8000

@celery_app.task(bind=True, autoretry_for=(ClientError, OperationalError), retry_kwargs={'max_retries': 3, 'countdown': 60})
def segment_and_tokenize_task(self, media_id: int) -> str:
    task_id = self.request.id
    logger.info(f"S&T(TaskID:{task_id}): Starting for media_id: {media_id}. Attempt: {self.request.retries + 1}")
    s3_client = get_s3_client()
    if not s3_client: 
        logger.error(f"S&T(TaskID:{task_id}): S3 client unavailable for media_id {media_id}. Cannot proceed.")
        return f"S&T: Error - S3 client unavailable for media_id {media_id}."

    task_temp_dir = tempfile.mkdtemp(dir=settings.TASK_TEMP_BASE_DIR)
    try:
        with Session(engine) as session:
            media_record = session.get(Media, media_id)
            if not media_record: 
                logger.error(f"S&T(TaskID:{task_id}): Media record {media_id} not found.")
                return f"S&T: Error - Media record {media_id} not found."
            if not media_record.transcription_path: 
                logger.error(f"S&T(TaskID:{task_id}): Transcription S3 key missing for media_id {media_id}.")
                return f"S&T: Error - Transcription S3 key missing for media_id {media_id}."
            
            processing_language = media_record.language if media_record.language else settings.DEFAULT_PROCESSING_LANGUAGE
            if not processing_language:
                logger.error(f"S&T(TaskID:{task_id}): Language not set for media_id {media_id} and no default configured.")
                return f"S&T: Error - Language not set for media_id {media_id} and no default configured."

            transcription_s3_key = media_record.transcription_path
            local_transcription_filename = f"{media_id}_transcription_downloaded.json"
            local_transcription_path = os.path.join(task_temp_dir, local_transcription_filename)

            logger.info(f"S&T(TaskID:{task_id}): Downloading {transcription_s3_key} to {local_transcription_path} for media_id {media_id}")
            if not download_file_from_s3(settings.S3_BUCKET_NAME, transcription_s3_key, local_transcription_path, s3_client):
                logger.error(f"S&T(TaskID:{task_id}): Failed to download transcription from S3 for media_id {media_id}.")
                raise Exception(f"S3 download failed for {transcription_s3_key}")

            logger.info(f"S&T(TaskID:{task_id}): Loading transcription JSON for media_id {media_id}")
            with open(local_transcription_path, "r", encoding="utf-8") as f:
                transcription_data = json.load(f)
            
            # Dynamic plugin loading
            logger.info(f"S&T(TaskID:{task_id}): Attempting to load language plugin for '{processing_language}' for media_id {media_id}")
            lang_plugin = get_language_plugin(processing_language)

            if not lang_plugin:
                logger.warning(f"S&T(TaskID:{task_id}): No language plugin found for '{processing_language}' for media_id {media_id}. SubtitleCue creation will be skipped.")
                generate_webvtt_task.delay(media_id) # Proceed to VTT generation (might be empty)
                return f"S&T(TaskID:{task_id}): No language plugin for '{processing_language}'. SubtitleCue creation skipped for media_id {media_id}."

            all_words_from_transcription = []
            logger.info(f"S&T(TaskID:{task_id}): Extracting words from transcription for media_id {media_id}")
            for seg_idx, segment in enumerate(transcription_data.get("segments", [])):
                for word_idx, word_info in enumerate(segment.get("words", [])):
                    if isinstance(word_info, dict) and 'word' in word_info and 'start' in word_info and 'end' in word_info:
                        all_words_from_transcription.append({
                            "text": word_info["word"],
                            "start_ms": int(float(word_info["start"]) * 1000),
                            "end_ms": int(float(word_info["end"]) * 1000),
                        })
            
            if not all_words_from_transcription:
                logger.info(f"S&T(TaskID:{task_id}): No words in transcription for media {media_id}. No cues created.")
                generate_webvtt_task.delay(media_id) 
                return f"S&T(TaskID:{task_id}): No words to segment for media {media_id}."

            logger.info(f"S&T(TaskID:{task_id}): Deleting existing cues for media_id {media_id} (if any).")
            existing_cues = session.exec(select(SubtitleCue).where(SubtitleCue.media_id == media_id)).all()
            if existing_cues:
                for cue in existing_cues: session.delete(cue)
                session.commit()

            logger.info(f"S&T(TaskID:{task_id}): Generating new cues for media_id {media_id}.")
            cue_count = 0
            current_cue_text_parts = []
            current_cue_start_ms = all_words_from_transcription[0]["start_ms"]
            last_word_end_ms = current_cue_start_ms

            for i, word_data in enumerate(all_words_from_transcription):
                word_text_segment = word_data["text"]
                word_start_ms = word_data["start_ms"] 
                word_end_ms = word_data["end_ms"]     
                
                if not current_cue_text_parts: 
                    current_cue_start_ms = word_start_ms 
                
                current_cue_duration = word_end_ms - current_cue_start_ms

                if (current_cue_duration > CUE_MAX_DURATION_MS and current_cue_text_parts) or \
                   (i == len(all_words_from_transcription) - 1):
                    
                    if i == len(all_words_from_transcription) - 1 :
                        current_cue_text_parts.append(word_text_segment)
                        final_cue_end_ms = word_end_ms
                    else: 
                        final_cue_end_ms = last_word_end_ms 

                    cue_text_to_process = "".join(current_cue_text_parts).strip()
                    markdown_output_parts = []

                    # Use the loaded lang_plugin here
                    if lang_plugin and cue_text_to_process:
                        tokens = lang_plugin.tokenize(cue_text_to_process)
                        for token in tokens:
                            surface, lemma = token['surface'], token['lemma']
                            db_word = session.exec(select(Word).where(Word.lemma == lemma, Word.language == processing_language)).first()
                            if not db_word:
                                db_word = Word(lemma=lemma, language=processing_language)
                                session.add(db_word)
                                session.flush() 
                            markdown_output_parts.append(f'<span class="w-0" data-wid="{db_word.id}">{surface}</span>')
                    elif cue_text_to_process: 
                        markdown_output_parts.append(cue_text_to_process) # Fallback for no plugin with tokenization
                    
                    if markdown_output_parts:
                        new_cue = SubtitleCue(
                            media_id=media_id, start_ms=current_cue_start_ms,
                            end_ms=final_cue_end_ms, text_markdown="".join(markdown_output_parts)
                        )
                        session.add(new_cue)
                        cue_count += 1
                    
                    if i == len(all_words_from_transcription) - 1 : 
                        current_cue_text_parts = [] 
                    else: 
                        current_cue_text_parts = [word_text_segment] if not (current_cue_duration > CUE_MAX_DURATION_MS and current_cue_text_parts) else []
                        current_cue_start_ms = word_start_ms if current_cue_text_parts else (all_words_from_transcription[i+1]["start_ms"] if i+1 < len(all_words_from_transcription) else word_end_ms)
                else: 
                    current_cue_text_parts.append(word_text_segment)
                last_word_end_ms = word_end_ms
            
            session.commit()
            logger.info(f"S&T(TaskID:{task_id}): Created {cue_count} cues for media_id {media_id}.")
            generate_webvtt_task.delay(media_id)
            return f"S&T(TaskID:{task_id}): Cue generation complete for media {media_id}, {cue_count} cues."
    except (ClientError, OperationalError) as exc:
        logger.warning(f"S&T(TaskID:{task_id}): Retrying for media_id {media_id} due to {type(exc).__name__}: {exc}. Attempt: {self.request.retries + 1}")
        raise
    except Exception as e:
        logger.exception(f"S&T(TaskID:{task_id}): Unexpected error for media_id {media_id}: {e}")
        return f"S&T(TaskID:{task_id}): Unexpected error for media_id {media_id}: {str(e)}"
    finally:
        if os.path.exists(task_temp_dir):
            shutil.rmtree(task_temp_dir)
            logger.info(f"S&T(TaskID:{task_id}): Cleaned temp dir {task_temp_dir} for media_id {media_id}")


def format_ms_to_webvtt_timestamp(ms: int) -> str:
    if ms < 0: ms = 0 
    seconds, milliseconds = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

@celery_app.task(bind=True, autoretry_for=(ClientError, OperationalError), retry_kwargs={'max_retries': 3, 'countdown': 60})
def generate_webvtt_task(self, media_id: int) -> str:
    task_id = self.request.id
    logger.info(f"WebVTT(TaskID:{task_id}): Starting for media_id: {media_id}. Attempt: {self.request.retries + 1}")
    s3_client = get_s3_client()
    if not s3_client: 
        logger.error(f"WebVTT(TaskID:{task_id}): S3 client unavailable for media_id {media_id}. Cannot proceed.")
        return f"WebVTT: Error - S3 client unavailable for media_id {media_id}."

    task_temp_dir = tempfile.mkdtemp(dir=settings.TASK_TEMP_BASE_DIR)
    try:
        with Session(engine) as session:
            media_record = session.get(Media, media_id)
            if not media_record: 
                logger.error(f"WebVTT(TaskID:{task_id}): Media record {media_id} not found.")
                return f"WebVTT: Error - Media record {media_id} not found."

            logger.info(f"WebVTT(TaskID:{task_id}): Fetching cues for media_id {media_id}.")
            statement = select(SubtitleCue).where(SubtitleCue.media_id == media_id).order_by(SubtitleCue.start_ms)
            cues = session.exec(statement).all()
            
            vtt_content_parts = ["WEBVTT\n"]
            if not cues:
                logger.info(f"WebVTT(TaskID:{task_id}): No cues for media_id {media_id}. Creating VTT with header only.")
            else:
                logger.info(f"WebVTT(TaskID:{task_id}): Formatting {len(cues)} cues for media_id {media_id}.")
                for cue in cues:
                    start_time = format_ms_to_webvtt_timestamp(cue.start_ms)
                    end_time = format_ms_to_webvtt_timestamp(cue.end_ms)
                    if cue.start_ms >= cue.end_ms: end_time = format_ms_to_webvtt_timestamp(cue.start_ms + 100)
                    vtt_content_parts.append(f"\n{start_time} --> {end_time}\n{cue.text_markdown}\n")
            
            full_vtt_content = "".join(vtt_content_parts)
            
            slug_title = "".join(c if c.isalnum() else "_" for c in media_record.title).strip("_")[:50] or "untitled"
            vtt_filename = f"{media_id}_{slug_title}.vtt"
            local_vtt_path = os.path.join(task_temp_dir, vtt_filename)
            
            logger.info(f"WebVTT(TaskID:{task_id}): Saving VTT content locally to {local_vtt_path} for media_id {media_id}")
            with open(local_vtt_path, "w", encoding="utf-8") as f:
                f.write(full_vtt_content)

            vtt_s3_key = f"{S3_WEBVTT_PREFIX}/{media_id}/{vtt_filename}"
            logger.info(f"WebVTT(TaskID:{task_id}): Uploading {local_vtt_path} to S3 as {vtt_s3_key} for media_id {media_id}")
            if not upload_file_to_s3(local_vtt_path, settings.S3_BUCKET_NAME, vtt_s3_key, s3_client):
                logger.error(f"WebVTT(TaskID:{task_id}): Failed to upload WebVTT to S3 for media_id {media_id}.")
                raise Exception(f"S3 upload failed for {vtt_s3_key}")

            media_record.webvtt_path = vtt_s3_key
            session.add(media_record)
            session.commit()
            session.refresh(media_record)
            logger.info(f"WebVTT(TaskID:{task_id}): S3 key {vtt_s3_key} saved for media_id {media_id}.")
            return f"WebVTT(TaskID:{task_id}): Success for media_id {media_id}: {vtt_s3_key}"
    except (ClientError, OperationalError) as exc:
        logger.warning(f"WebVTT(TaskID:{task_id}): Retrying for media_id {media_id} due to {type(exc).__name__}: {exc}. Attempt: {self.request.retries + 1}")
        raise
    except Exception as e:
        logger.exception(f"WebVTT(TaskID:{task_id}): Unexpected error for media_id {media_id}: {e}")
        return f"WebVTT(TaskID:{task_id}): Unexpected error for media_id {media_id}: {str(e)}"
    finally:
        if os.path.exists(task_temp_dir):
            shutil.rmtree(task_temp_dir)
            logger.info(f"WebVTT(TaskID:{task_id}): Cleaned temp dir {task_temp_dir} for media_id {media_id}")

@celery_app.task(name="process_subtitle")
def process_subtitle(subtitle_id: int, language: str):
    logger.warning(f"Task 'process_subtitle' (ID: {subtitle_id}, Lang: {language}) is not S3 integrated and is a placeholder.")
    return "This task (process_subtitle) is a placeholder and not S3 integrated."

@celery_app.task(name="nlp_process_word")
def nlp_process_word(word_id: int, language: str):
    logger.warning(f"Task 'nlp_process_word' (ID: {word_id}, Lang: {language}) is not S3 integrated and is a placeholder.")
    return "This task (nlp_process_word) is a placeholder and not S3 integrated."
