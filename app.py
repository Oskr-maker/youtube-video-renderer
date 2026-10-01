        ["ffmpeg", "-version"],
        capture_output=True,
        text=True
    )

    first_line = result.stdout.splitlines()[0] if result.stdout else ""

    return {
        "status": "ok",
        "ffmpeg": first_line
    }
