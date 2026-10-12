from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from typing import List
import subprocess
import tempfile
import os
import json
import shutil


app = FastAPI()


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


@app.post("/concat-audio")
async def concat_audio(
    files: List[UploadFile] = File(...),
    pauses: str = Form("[]")
):
    """
    Recibe varios archivos de audio en orden y los concatena
    añadiendo silencios entre ellos.

    Form-data esperado:
    - files: múltiples archivos mp3
    - pauses: JSON string con pausas en milisegundos
      Ejemplo:
      [350, 300, 450, 450, 450, 450, 250]
    """

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

        # -------------------------------------------------
        # Guardar archivos recibidos
        # -------------------------------------------------

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

            with open(input_path, "wb") as audio_file:
                audio_file.write(content)

            input_paths.append(input_path)

        # -------------------------------------------------
        # Construir entradas FFmpeg
        # -------------------------------------------------

        ffmpeg_inputs = []

        for path in input_paths:
            ffmpeg_inputs.extend([
                "-i",
                path
            ])

        # -------------------------------------------------
        # Normalizar cada audio
        # -------------------------------------------------

        filter_parts = []

        for index in range(len(input_paths)):
            filter_parts.append(
                f"[{index}:a]"
                f"aresample=48000,"
                f"aformat=sample_fmts=fltp:"
                f"sample_rates=48000:"
                f"channel_layouts=stereo"
                f"[a{index}]"
            )

        # -------------------------------------------------
        # Crear silencios entre chunks
        # -------------------------------------------------

        concat_labels = []

        for index in range(len(input_paths)):
            concat_labels.append(
                f"[a{index}]"
            )

            # No añadir silencio después del último audio
            if index < len(input_paths) - 1:

                if index < len(pause_values):
                    pause_ms = pause_values[index]
                else:
                    pause_ms = 300

                try:
                    pause_ms = float(pause_ms)
                except Exception:
                    pause_ms = 300

                pause_ms = max(
                    0,
                    pause_ms
                )

                pause_seconds = pause_ms / 1000.0

                filter_parts.append(
                    f"anullsrc="
                    f"channel_layout=stereo:"
                    f"sample_rate=48000,"
                    f"atrim=duration={pause_seconds}"
                    f"[s{index}]"
                )

                concat_labels.append(
                    f"[s{index}]"
                )

        # -------------------------------------------------
        # Concatenar audio + silencios
        # -------------------------------------------------

        concat_count = len(concat_labels)

        concat_filter = (
            "".join(concat_labels)
            + f"concat=n={concat_count}:v=0:a=1[outa]"
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

        # -------------------------------------------------
        # Ejecutar FFmpeg
        # -------------------------------------------------

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
                    "message": "FFmpeg audio concat failed",
                    "ffmpeg_error": result.stderr
                }
            )

        # -------------------------------------------------
        # Copiar resultado fuera del tempdir
        # -------------------------------------------------

        final_path = "/tmp/voice_final_kokoro.mp3"

        shutil.copyfile(
            output_path,
            final_path
        )

    return FileResponse(
        final_path,
        media_type="audio/mpeg",
        filename="voice_final_kokoro.mp3"
    )


@app.post("/render")
async def render_video(
    audio: UploadFile = File(...),
    manifest: str = Form(...)
):
    try:
        data = json.loads(manifest)
    except Exception as error:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": f"Invalid manifest JSON: {str(error)}"
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
                    "message": "Audio file is empty"
                }
            )

        with open(audio_path, "wb") as audio_file:
            audio_file.write(audio_content)

        title = data.get(
            "title",
            "AI Video"
        )

        # Escapar caracteres problemáticos para drawtext
        safe_title = (
            str(title)
            .replace("\\", "\\\\")
            .replace(":", "\\:")
            .replace("'", "\\'")
            .replace("%", "\\%")
        )

        command = [
            "ffmpeg",
            "-y",

            "-f",
            "lavfi",

            "-i",
            "color=c=black:s=1920x1080:r=30",

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
                    "message": "FFmpeg video render failed",
                    "ffmpeg_error": result.stderr
                }
            )

        final_path = "/tmp/final_video.mp4"

        shutil.copyfile(
            output_path,
            final_path
        )

    return FileResponse(
        final_path,
        media_type="video/mp4",
        filename="final_video.mp4"
    )
