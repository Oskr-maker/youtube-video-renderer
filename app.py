from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from typing import List
import subprocess
import tempfile
import os
import json
import shutil


app = FastAPI()


# =====================================================
# HELPERS
# =====================================================

def parse_fraction(value):
    """
    Convierte valores de ffprobe como:
    30/1
    30000/1001
    en float.
    """

    if value is None:
        return None

    try:
        value = str(value)

        if "/" in value:
            numerator, denominator = value.split("/", 1)

            numerator = float(numerator)
            denominator = float(denominator)

            if denominator == 0:
                return None

            return numerator / denominator

        return float(value)

    except Exception:
        return None


def safe_float(value):
    if value is None:
        return None

    try:
        return float(value)
    except Exception:
        return None


# =====================================================
# HEALTH
# =====================================================

@app.get("/health")
def health():
    result = subprocess.run(
        ["ffmpeg", "-version"],
        capture_output=True,
        text=True
    )

    first_line = (
        result.stdout.splitlines()[0]
        if result.stdout
        else ""
    )

    ffprobe_result = subprocess.run(
        ["ffprobe", "-version"],
        capture_output=True,
        text=True
    )

    ffprobe_first_line = (
        ffprobe_result.stdout.splitlines()[0]
        if ffprobe_result.stdout
        else ""
    )

    return {
        "status": "ok",
        "ffmpeg": first_line,
        "ffprobe": ffprobe_first_line
    }


# =====================================================
# CONCAT AUDIO
# =====================================================

@app.post("/concat-audio")
async def concat_audio(
    files: List[UploadFile] = File(...),
    pauses: str = Form("[]")
):
    if not files:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "No audio files received"
            }
        )

    try:
        pause_values = json.loads(
            pauses
        )

    except Exception as error:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message":
                    f"Invalid pauses JSON: {str(error)}"
            }
        )

    if not isinstance(
        pause_values,
        list
    ):
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message":
                    "pauses must be a JSON array"
            }
        )

    with tempfile.TemporaryDirectory() as tmpdir:

        input_paths = []

        for index, upload in enumerate(
            files
        ):

            input_path = os.path.join(
                tmpdir,
                f"chunk_{index:03d}.mp3"
            )

            content = await upload.read()

            if not content:
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message":
                            f"Empty audio file at index {index}"
                    }
                )

            with open(
                input_path,
                "wb"
            ) as audio_file:
                audio_file.write(
                    content
                )

            input_paths.append(
                input_path
            )

        ffmpeg_inputs = []

        for path in input_paths:
            ffmpeg_inputs.extend([
                "-i",
                path
            ])

        filter_parts = []

        for index in range(
            len(input_paths)
        ):

            filter_parts.append(
                f"[{index}:a]"
                f"aresample=48000,"
                f"aformat="
                f"sample_fmts=fltp:"
                f"sample_rates=48000:"
                f"channel_layouts=stereo"
                f"[a{index}]"
            )

        concat_labels = []

        for index in range(
            len(input_paths)
        ):

            concat_labels.append(
                f"[a{index}]"
            )

            if index < (
                len(input_paths) - 1
            ):

                if index < len(
                    pause_values
                ):
                    pause_ms = (
                        pause_values[index]
                    )

                else:
                    pause_ms = 300

                try:
                    pause_ms = float(
                        pause_ms
                    )

                except Exception:
                    pause_ms = 300

                pause_ms = max(
                    0,
                    pause_ms
                )

                pause_seconds = (
                    pause_ms /
                    1000.0
                )

                filter_parts.append(
                    f"anullsrc="
                    f"channel_layout=stereo:"
                    f"sample_rate=48000,"
                    f"atrim=duration="
                    f"{pause_seconds}"
                    f"[s{index}]"
                )

                concat_labels.append(
                    f"[s{index}]"
                )

        concat_count = len(
            concat_labels
        )

        concat_filter = (
            "".join(
                concat_labels
            )
            +
            f"concat=n={concat_count}:"
            f"v=0:a=1[outa]"
        )

        filter_parts.append(
            concat_filter
        )

        filter_complex = ";".join(
            filter_parts
        )

        output_path = os.path.join(
            tmpdir,
            "voice_final_kokoro.mp3"
        )

        command = [
            "ffmpeg",
            "-y",

            *ffmpeg_inputs,

            "-filter_complex",
            filter_complex,

            "-map",
            "[outa]",

            "-c:a",
            "libmp3lame",

            "-b:a",
            "192k",

            "-ar",
            "48000",

            "-ac",
            "2",

            output_path
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message":
                        "FFmpeg audio concat failed",
                    "ffmpeg_error":
                        result.stderr
                }
            )

        final_path = (
            "/tmp/"
            "voice_final_kokoro.mp3"
        )

        shutil.copyfile(
            output_path,
            final_path
        )

    return FileResponse(
        final_path,
        media_type="audio/mpeg",
        filename=
            "voice_final_kokoro.mp3"
    )


# =====================================================
# CONCAT VIDEO SECTIONS V4
# =====================================================

@app.post("/concat-video")
async def concat_video(
    files: List[UploadFile] = File(...)
):
    if not files:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message":
                    "No video files received"
            }
        )

    with tempfile.TemporaryDirectory() as tmpdir:

        input_paths = []

        for index, upload in enumerate(
            files
        ):

            content = await upload.read()

            if not content:
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message":
                            f"Empty video file at index {index}"
                    }
                )

            input_path = os.path.join(
                tmpdir,
                f"section_{index:03d}.mp4"
            )

            with open(
                input_path,
                "wb"
            ) as video_file:
                video_file.write(
                    content
                )

            input_paths.append(
                input_path
            )

        concat_list_path = os.path.join(
            tmpdir,
            "concat.txt"
        )

        with open(
            concat_list_path,
            "w",
            encoding="utf-8"
        ) as concat_file:

            for path in input_paths:

                safe_path = (
                    path.replace(
                        "'",
                        "'\\''"
                    )
                )

                concat_file.write(
                    f"file '{safe_path}'\n"
                )

        output_path = os.path.join(
            tmpdir,
            "youtube_v4_visual_concat.mp4"
        )

        copy_command = [
            "ffmpeg",
            "-y",

            "-f",
            "concat",

            "-safe",
            "0",

            "-i",
            concat_list_path,

            "-c",
            "copy",

            "-movflags",
            "+faststart",

            output_path
        ]

        copy_result = subprocess.run(
            copy_command,
            capture_output=True,
            text=True
        )

        if copy_result.returncode != 0:

            normalized_paths = []

            for index, input_path in enumerate(
                input_paths
            ):

                normalized_path = os.path.join(
                    tmpdir,
                    f"normalized_{index:03d}.mp4"
                )

                normalize_command = [
                    "ffmpeg",
                    "-y",

                    "-i",
                    input_path,

                    "-an",

                    "-vf",
                    (
                        "scale=1920:1080:"
                        "force_original_aspect_ratio="
                        "decrease,"
                        "pad=1920:1080:"
                        "(ow-iw)/2:"
                        "(oh-ih)/2,"
                        "fps=30"
                    ),

                    "-c:v",
                    "libx264",

                    "-preset",
                    "medium",

                    "-crf",
                    "20",

                    "-pix_fmt",
                    "yuv420p",

                    "-movflags",
                    "+faststart",

                    normalized_path
                ]

                normalize_result = (
                    subprocess.run(
                        normalize_command,
                        capture_output=True,
                        text=True
                    )
                )

                if (
                    normalize_result.returncode
                    != 0
                ):
                    return JSONResponse(
                        status_code=500,
                        content={
                            "status":
                                "error",
                            "message":
                                "FFmpeg normalization failed",
                            "section":
                                index + 1,
                            "ffmpeg_error":
                                normalize_result.stderr
                        }
                    )

                normalized_paths.append(
                    normalized_path
                )

            normalized_list_path = (
                os.path.join(
                    tmpdir,
                    "concat_normalized.txt"
                )
            )

            with open(
                normalized_list_path,
                "w",
                encoding="utf-8"
            ) as concat_file:

                for path in normalized_paths:

                    safe_path = (
                        path.replace(
                            "'",
                            "'\\''"
                        )
                    )

                    concat_file.write(
                        f"file '{safe_path}'\n"
                    )

            final_command = [
                "ffmpeg",
                "-y",

                "-f",
                "concat",

                "-safe",
                "0",

                "-i",
                normalized_list_path,

                "-c",
                "copy",

                "-movflags",
                "+faststart",

                output_path
            ]

            final_result = subprocess.run(
                final_command,
                capture_output=True,
                text=True
            )

            if (
                final_result.returncode
                != 0
            ):
                return JSONResponse(
                    status_code=500,
                    content={
                        "status":
                            "error",
                        "message":
                            "FFmpeg final concat failed",
                        "ffmpeg_error":
                            final_result.stderr
                    }
                )

        final_path = (
            "/tmp/"
            "youtube_v4_visual_concat.mp4"
        )

        shutil.copyfile(
            output_path,
            final_path
        )

    return FileResponse(
        final_path,
        media_type="video/mp4",
        filename=
            "youtube_v4_visual_concat.mp4"
    )


# =====================================================
# MUX VIDEO V4 + KOKORO AUDIO
# =====================================================

@app.post("/mux-video-audio")
async def mux_video_audio(
    video: UploadFile = File(...),
    audio: UploadFile = File(...)
):
    video_content = await video.read()
    audio_content = await audio.read()

    if not video_content:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message":
                    "Video file is empty"
            }
        )

    if not audio_content:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message":
                    "Audio file is empty"
            }
        )

    with tempfile.TemporaryDirectory() as tmpdir:

        video_path = os.path.join(
            tmpdir,
            "video_v4.mp4"
        )

        audio_path = os.path.join(
            tmpdir,
            "voice_final_kokoro.mp3"
        )

        output_path = os.path.join(
            tmpdir,
            "youtube_v4_final_with_audio.mp4"
        )

        with open(
            video_path,
            "wb"
        ) as video_file:
            video_file.write(
                video_content
            )

        with open(
            audio_path,
            "wb"
        ) as audio_file:
            audio_file.write(
                audio_content
            )

        command = [
            "ffmpeg",
            "-y",

            "-i",
            video_path,

            "-i",
            audio_path,

            "-map",
            "0:v:0",

            "-map",
            "1:a:0",

            "-c:v",
            "copy",

            "-c:a",
            "aac",

            "-b:a",
            "192k",

            "-ar",
            "48000",

            "-ac",
            "2",

            "-af",
            "apad",

            "-shortest",

            "-movflags",
            "+faststart",

            output_path
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message":
                        "FFmpeg video/audio mux failed",
                    "ffmpeg_error":
                        result.stderr
                }
            )

        if not os.path.exists(
            output_path
        ):
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message":
                        "MUX output file was not created"
                }
            )

        if os.path.getsize(
            output_path
        ) <= 0:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message":
                        "MUX output file is empty"
                }
            )

        final_path = (
            "/tmp/"
            "youtube_v4_final_with_audio.mp4"
        )

        shutil.copyfile(
            output_path,
            final_path
        )

    return FileResponse(
        final_path,
        media_type="video/mp4",
        filename=
            "youtube_v4_final_with_audio.mp4"
    )


# =====================================================
# FINAL VIDEO QC / INSPECTION
# =====================================================

@app.post("/inspect-video")
async def inspect_video(
    file: UploadFile = File(...)
):
    """
    QC técnico final del MP4.

    Comprueba:
    - vídeo presente
    - audio presente
    - H.264
    - AAC
    - 1920x1080
    - ~30 FPS
    - duración válida
    - sincronía temporal aproximada A/V
    """

    content = await file.read()

    if not content:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message":
                    "Video file is empty",
                "qcPassed":
                    False
            }
        )

    with tempfile.TemporaryDirectory() as tmpdir:

        input_path = os.path.join(
            tmpdir,
            "final_v4.mp4"
        )

        with open(
            input_path,
            "wb"
        ) as video_file:
            video_file.write(
                content
            )

        # -------------------------------------------------
        # FFPROBE
        # -------------------------------------------------

        command = [
            "ffprobe",
            "-v",
            "error",

            "-print_format",
            "json",

            "-show_format",

            "-show_streams",

            input_path
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message":
                        "FFprobe inspection failed",
                    "ffprobe_error":
                        result.stderr,
                    "qcPassed":
                        False
                }
            )

        try:
            probe = json.loads(
                result.stdout
            )

        except Exception as error:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message":
                        f"Could not parse ffprobe JSON: {str(error)}",
                    "qcPassed":
                        False
                }
            )

        streams = probe.get(
            "streams",
            []
        )

        format_data = probe.get(
            "format",
            {}
        )

        video_stream = next(
            (
                stream
                for stream in streams
                if stream.get(
                    "codec_type"
                ) == "video"
            ),
            None
        )

        audio_stream = next(
            (
                stream
                for stream in streams
                if stream.get(
                    "codec_type"
                ) == "audio"
            ),
            None
        )

        has_video = (
            video_stream
            is not None
        )

        has_audio = (
            audio_stream
            is not None
        )

        # -------------------------------------------------
        # VIDEO DATA
        # -------------------------------------------------

        width = (
            int(
                video_stream.get(
                    "width",
                    0
                )
            )
            if has_video
            else 0
        )

        height = (
            int(
                video_stream.get(
                    "height",
                    0
                )
            )
            if has_video
            else 0
        )

        video_codec = (
            video_stream.get(
                "codec_name"
            )
            if has_video
            else None
        )

        pixel_format = (
            video_stream.get(
                "pix_fmt"
            )
            if has_video
            else None
        )

        fps = None

        if has_video:
            fps = parse_fraction(
                video_stream.get(
                    "avg_frame_rate"
                )
            )

            if fps is None:
                fps = parse_fraction(
                    video_stream.get(
                        "r_frame_rate"
                    )
                )

        # -------------------------------------------------
        # AUDIO DATA
        # -------------------------------------------------

        audio_codec = (
            audio_stream.get(
                "codec_name"
            )
            if has_audio
            else None
        )

        audio_sample_rate = (
            int(
                audio_stream.get(
                    "sample_rate",
                    0
                )
            )
            if (
                has_audio
                and audio_stream.get(
                    "sample_rate"
                )
            )
            else None
        )

        audio_channels = (
            int(
                audio_stream.get(
                    "channels",
                    0
                )
            )
            if has_audio
            else None
        )

        # -------------------------------------------------
        # DURATIONS
        # -------------------------------------------------

        format_duration = safe_float(
            format_data.get(
                "duration"
            )
        )

        video_duration = (
            safe_float(
                video_stream.get(
                    "duration"
                )
            )
            if has_video
            else None
        )

        audio_duration = (
            safe_float(
                audio_stream.get(
                    "duration"
                )
            )
            if has_audio
            else None
        )

        # Algunos MP4 no guardan duración individual
        # en todos los streams.
        if (
            video_duration is None
            and format_duration is not None
        ):
            video_duration = (
                format_duration
            )

        if (
            audio_duration is None
            and format_duration is not None
        ):
            audio_duration = (
                format_duration
            )

        av_duration_diff = None

        if (
            video_duration is not None
            and audio_duration is not None
        ):
            av_duration_diff = abs(
                video_duration -
                audio_duration
            )

        # -------------------------------------------------
        # FILE DATA
        # -------------------------------------------------

        file_size_bytes = len(
            content
        )

        file_size_mb = (
            file_size_bytes /
            1024 /
            1024
        )

        format_name = (
            format_data.get(
                "format_name"
            )
        )

        # -------------------------------------------------
        # QC
        # -------------------------------------------------

        errors = []
        warnings = []

        if not has_video:
            errors.append(
                "Video stream missing"
            )

        if not has_audio:
            errors.append(
                "Audio stream missing"
            )

        if has_video:

            if video_codec != "h264":
                errors.append(
                    f"Unexpected video codec: {video_codec}"
                )

            if (
                width != 1920
                or height != 1080
            ):
                errors.append(
                    f"Unexpected resolution: {width}x{height}"
                )

            if fps is None:
                errors.append(
                    "FPS could not be determined"
                )

            elif not (
                29.8 <= fps <= 30.2
            ):
                errors.append(
                    f"Unexpected FPS: {fps:.3f}"
                )

            if pixel_format not in [
                "yuv420p",
                "yuvj420p"
            ]:
                warnings.append(
                    f"Unexpected pixel format: {pixel_format}"
                )

        if has_audio:

            if audio_codec != "aac":
                errors.append(
                    f"Unexpected audio codec: {audio_codec}"
                )

            if (
                audio_sample_rate is not None
                and audio_sample_rate != 48000
            ):
                warnings.append(
                    f"Audio sample rate is {audio_sample_rate}, expected 48000"
                )

            if (
                audio_channels is not None
                and audio_channels != 2
            ):
                warnings.append(
                    f"Audio has {audio_channels} channels, expected stereo"
                )

        if (
            format_duration is None
            or format_duration <= 0
        ):
            errors.append(
                "Invalid total duration"
            )

        if (
            av_duration_diff is not None
        ):

            if av_duration_diff > 0.50:
                errors.append(
                    f"Audio/video duration mismatch: {av_duration_diff:.3f}s"
                )

            elif av_duration_diff > 0.20:
                warnings.append(
                    f"Minor audio/video duration difference: {av_duration_diff:.3f}s"
                )

        if file_size_bytes <= 0:
            errors.append(
                "Final file is empty"
            )

        qc_passed = (
            len(errors) == 0
        )

        # -------------------------------------------------
        # RESULT
        # -------------------------------------------------

        return {
            "status":
                "ok"
                if qc_passed
                else "qc_failed",

            "qcVersion":
                "v1_final_mp4_technical_qc",

            "qcPassed":
                qc_passed,

            "hasVideo":
                has_video,

            "hasAudio":
                has_audio,

            "durationSec":
                (
                    round(
                        format_duration,
                        3
                    )
                    if format_duration
                    is not None
                    else None
                ),

            "videoDurationSec":
                (
                    round(
                        video_duration,
                        3
                    )
                    if video_duration
                    is not None
                    else None
                ),

            "audioDurationSec":
                (
                    round(
                        audio_duration,
                        3
                    )
                    if audio_duration
                    is not None
                    else None
                ),

            "avDurationDiffSec":
                (
                    round(
                        av_duration_diff,
                        3
                    )
                    if av_duration_diff
                    is not None
                    else None
                ),

            "width":
                width,

            "height":
                height,

            "fps":
                (
                    round(
                        fps,
                        3
                    )
                    if fps
                    is not None
                    else None
                ),

            "videoCodec":
                video_codec,

            "pixelFormat":
                pixel_format,

            "audioCodec":
                audio_codec,

            "audioSampleRate":
                audio_sample_rate,

            "audioChannels":
                audio_channels,

            "formatName":
                format_name,

            "fileSizeBytes":
                file_size_bytes,

            "fileSizeMB":
                round(
                    file_size_mb,
                    2
                ),

            "errors":
                errors,

            "warnings":
                warnings
        }


# =====================================================
# OLD VIDEO RENDERER
# =====================================================

@app.post("/render")
async def render_video(
    audio: UploadFile = File(...),
    manifest: str = Form(...)
):
    try:
        data = json.loads(
            manifest
        )

    except Exception as error:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message":
                    f"Invalid manifest JSON: {str(error)}"
            }
        )

    with tempfile.TemporaryDirectory() as tmpdir:

        audio_path = os.path.join(
            tmpdir,
            "audio.mp3"
        )

        output_path = os.path.join(
            tmpdir,
            "output.mp4"
        )

        audio_content = (
            await audio.read()
        )

        if not audio_content:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message":
                        "Audio file is empty"
                }
            )

        with open(
            audio_path,
            "wb"
        ) as audio_file:
            audio_file.write(
                audio_content
            )

        title = data.get(
            "title",
            "AI Video"
        )

        safe_title = (
            str(title)
            .replace(
                "\\",
                "\\\\"
            )
            .replace(
                ":",
                "\\:"
            )
            .replace(
                "'",
                "\\'"
            )
            .replace(
                "%",
                "\\%"
            )
        )

        command = [
            "ffmpeg",
            "-y",

            "-f",
            "lavfi",

            "-i",
            (
                "color=c=black:"
                "s=1920x1080:"
                "r=30"
            ),

            "-i",
            audio_path,

            "-vf",
            (
                f"drawtext="
                f"text='{safe_title}':"
                f"fontcolor=white:"
                f"fontsize=60:"
                f"x=(w-text_w)/2:"
                f"y=(h-text_h)/2"
            ),

            "-c:v",
            "libx264",

            "-preset",
            "medium",

            "-crf",
            "23",

            "-c:a",
            "aac",

            "-b:a",
            "192k",

            "-shortest",

            output_path
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message":
                        "FFmpeg video render failed",
                    "ffmpeg_error":
                        result.stderr
                }
            )

        final_path = (
            "/tmp/final_video.mp4"
        )

        shutil.copyfile(
            output_path,
            final_path
        )

    return FileResponse(
        final_path,
        media_type="video/mp4",
        filename="final_video.mp4"
    )
