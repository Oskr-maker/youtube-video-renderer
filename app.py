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
# HEALTH
# =====================================================

@app.get("/health")
def health():
    result = subprocess.run(
        ["ffmpeg", "-version"],
        capture_output=True,
        text=True
    )

    first_line = result.stdout.splitlines()[0] if result.stdout else ""

    return {
        "status": "ok",
        "ffmpeg": first_line
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
        pause_values = json.loads(pauses)
    except Exception as error:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": f"Invalid pauses JSON: {str(error)}"
            }
        )

    if not isinstance(pause_values, list):
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "pauses must be a JSON array"
            }
        )

    with tempfile.TemporaryDirectory() as tmpdir:

        input_paths = []

        for index, upload in enumerate(files):

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
                        "message": f"Empty audio file at index {index}"
                    }
                )

            with open(
                input_path,
                "wb"
            ) as audio_file:
                audio_file.write(content)

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

            if index < len(
                input_paths
            ) - 1:

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
    """
    Recibe múltiples MP4 ya ordenados y los concatena.

    Form-data:
    files = varios MP4

    Devuelve:
    youtube_v4_visual_concat.mp4
    """

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

        # -------------------------------------------------
        # GUARDAR SECCIONES
        # -------------------------------------------------

        for index, upload in enumerate(files):

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

        # -------------------------------------------------
        # CREAR LISTA CONCAT FFMPEG
        # -------------------------------------------------

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

        # -------------------------------------------------
        # PRIMER INTENTO:
        # CONCAT SIN RECODIFICAR
        # -------------------------------------------------

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

        # -------------------------------------------------
        # FALLBACK:
        # SI COPY FALLA, NORMALIZAR Y RECODIFICAR
        # -------------------------------------------------

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
                            "status": "error",
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
                        "status": "error",
                        "message":
                            "FFmpeg final concat failed",
                        "ffmpeg_error":
                            final_result.stderr
                    }
                )

        # -------------------------------------------------
        # COPIAR FUERA DEL TEMPDIR
        # -------------------------------------------------

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

        audio_content = await audio.read()

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
