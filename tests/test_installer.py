import io
import zipfile
from pathlib import Path
import pytest
from trollsound import installer


class Response(io.BytesIO):
    url = installer.DRIVER_URL


def test_modified_download_never_executes(tmp_path, monkeypatch):
    monkeypatch.setattr(installer.urllib.request, "urlopen", lambda *a, **k: Response(b"modified"))
    with pytest.raises(ValueError, match="no coincide"):
        installer.download_driver(tmp_path / "driver.zip")


def test_download_failure(qtbot, monkeypatch):
    def fail(*args):
        raise OSError("offline")
    monkeypatch.setattr(installer, "download_driver", fail)
    worker = installer.InstallWorker()
    with qtbot.waitSignal(worker.result, timeout=5000) as result:
        worker.start()
    worker.wait(5000)
    assert result.args[0] is False and "offline" in result.args[1]


def test_zip_traversal_rejected(tmp_path):
    archive = tmp_path / "malicious.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("../outside.exe", "bad")
    with pytest.raises(ValueError):
        installer.extract_driver(archive, tmp_path / "extract")
    assert not (tmp_path / "outside.exe").exists()


def test_decline_installer(qtbot):
    dialog = installer.InstallDialog()
    qtbot.addWidget(dialog)
    dialog.reject()
    assert dialog.code == 12 and dialog.worker is None


def test_driver_detected_requests_restart(qtbot, monkeypatch):
    monkeypatch.setattr(installer, "download_driver", lambda *a: None)
    monkeypatch.setattr(installer, "extract_driver", lambda *a: Path("fake.exe"))
    monkeypatch.setattr(installer, "run_elevated", lambda *a: 0)
    monkeypatch.setattr(installer, "native_endpoints", lambda: [object()])
    worker = installer.InstallWorker()
    with qtbot.waitSignal(worker.result, timeout=5000) as result:
        worker.start()
    worker.wait(5000)
    assert result.args[0] is True and "Reinicia" in result.args[1]
