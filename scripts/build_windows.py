"""Build the Windows distribution using the current virtual environment."""

from pathlib import Path
import subprocess
import sys
import shutil


def main():
    project = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "RetroBeaten.spec"],
        cwd=project, check=True,
    )
    shutil.copyfile(project / "WINDOWS.md", project / "dist/RetroBeaten/README.md")
    print(f"Executable: {project / 'dist/RetroBeaten/RetroBeaten.exe'}")


if __name__ == "__main__":
    main()
