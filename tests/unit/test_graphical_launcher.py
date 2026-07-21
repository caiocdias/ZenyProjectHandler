from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]


def test_graphical_launcher_uses_venv_pythonw_without_console() -> None:
    launcher_script = (PROJECT_ROOT / "ZenyProjectHandler.vbs").read_text(encoding="utf-8")

    assert ".venv\\Scripts\\pythonw.exe" in launcher_script
    assert " -m zeny_project_handler" in launcher_script
    assert "shell.CurrentDirectory = appDirectory" in launcher_script
    assert "shell.Run(command, 1, True)" in launcher_script
    assert "MsgBox" in launcher_script
