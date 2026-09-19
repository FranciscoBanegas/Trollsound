import os

os.environ["QT_MEDIA_BACKEND"] = "ffmpeg"

from trollsound.main import main

if __name__ == "__main__":
    raise SystemExit(main())
