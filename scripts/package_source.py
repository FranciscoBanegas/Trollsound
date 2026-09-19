"""Package project sources without local user data, binaries or downloaded drivers."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "dist" / "Trollsound-1.0.5-source.zip"
    output.parent.mkdir(exist_ok=True)
    paths = [root / name for name in ("launcher.py", "Trollsound.spec", "README.md", "THIRD_PARTY.md",
             "LICENSE", "VALIDATION.md", "requirements.txt", "requirements-build.txt", "pytest.ini", ".gitignore")]
    for name in ("trollsound", "scripts", "tests", "packaging", "licenses", "docs"):
        paths.extend(p for p in (root / name).rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and p.suffix != ".pyc")
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            archive.write(path, "Trollsound/" + path.relative_to(root).as_posix())
    print(output)


if __name__ == "__main__":
    main()
