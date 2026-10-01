from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse
import subprocess
import tempfile
import os
import json

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

@app.post("/render")
async def render_video(
    audio: UploadFile = File(...),
    manifest: str = Form(...)
):
    data = json.loads(manifest)

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "audio.mp3")
        output_path = os.path.join(tmpdir, "output.mp4")

        with open(audio_path, "wb") as f:
            f.write(await audio.read())

        title = data.get("title", "AI Video")

        command = [
            "ffmpeg",
            "-y",

            "-f", "lavfi",
            "-i", "color=c=black:s=1920x1080:r=30",

            "-i", audio_path,

            "-vf",
            f"drawtext=text='{title}':fontcolor=white:fontsize=60:"
            "x=(w-text_w)/2:y=(h-text_h)/2",

            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",

            "-c:a", "aac",
            "-b:a", "192k",

            "-shortest",

            output_path
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return {
                "status": "error",
                "ffmpeg_error": result.stderr
            }

        final_path = "/tmp/final_video.mp4"

        subprocess.run(
            ["cp", output_path, final_path]
        )

    return FileResponse(
        final_path,
        media_type="video/mp4",
        filename="final_video.mp4"
    )
