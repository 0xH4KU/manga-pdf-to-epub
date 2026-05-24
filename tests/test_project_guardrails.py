import ast
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


class ProjectGuardrailTests(unittest.TestCase):
    def test_root_only_keeps_project_level_files(self):
        self.assertFalse(Path("epub_layout_gui.py").exists())
        self.assertFalse(Path("pdf_to_epub_lossless.py").exists())
        self.assertTrue(Path("scripts/manga_to_epub.py").exists())
        self.assertTrue(Path("scripts/epub_layout_gui.py").exists())
        self.assertTrue(Path("scripts/pdf_to_epub_lossless.py").exists())

    def test_source_modules_are_grouped_by_responsibility(self):
        expected_packages = [
            Path("src/manga_pdf_to_epub/pdf"),
            Path("src/manga_pdf_to_epub/sources"),
            Path("src/manga_pdf_to_epub/epub"),
            Path("src/manga_pdf_to_epub/gui"),
            Path("src/manga_pdf_to_epub/models"),
        ]

        self.assertEqual([], [str(path) for path in expected_packages if not path.is_dir()])

    def test_gui_module_keeps_delete_history_in_dedicated_helper(self):
        source = Path("src/manga_pdf_to_epub/gui/layout_app.py").read_text(encoding="utf-8")
        self.assertIn("from .layout_history import CoverState, DeleteHistory", source)
        self.assertNotIn("deleted_cover_states", source)

    def test_gui_app_class_stays_below_current_complexity_ceiling(self):
        tree = ast.parse(Path("src/manga_pdf_to_epub/gui/layout_app.py").read_text(encoding="utf-8"))
        app_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "EpubLayoutApp")
        self.assertLessEqual(app_class.end_lineno - app_class.lineno + 1, 1200)

    def test_gui_series_workflow_lives_in_dedicated_controller(self):
        source = Path("src/manga_pdf_to_epub/gui/layout_app.py").read_text(encoding="utf-8")
        controller = Path("src/manga_pdf_to_epub/gui/layout_series_controller.py")

        self.assertTrue(controller.exists())
        self.assertIn("from .layout_series_controller import EpubLayoutSeriesMixin", source)

    def test_gui_behavior_tests_stay_split_by_workflow(self):
        test_files = [
            Path("tests/test_epub_layout_gui.py"),
            Path("tests/test_epub_layout_gui_commands.py"),
            Path("tests/test_epub_layout_gui_editing.py"),
            Path("tests/test_epub_layout_gui_preview.py"),
            Path("tests/test_epub_layout_gui_project.py"),
            Path("tests/test_epub_layout_gui_series.py"),
        ]

        missing = [str(path) for path in test_files if not path.exists()]
        self.assertEqual([], missing)
        for path in test_files:
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertLessEqual(len(lines), 550, str(path))

    def test_cbz_export_files_are_removed(self):
        removed_paths = [
            Path("pdf_to_cbz_lossless.py"),
            Path("src/manga_pdf_to_epub/pdf_to_cbz_lossless.py"),
            Path("tests/test_pdf_to_cbz_lossless.py"),
        ]

        self.assertEqual([], [str(path) for path in removed_paths if path.exists()])

    def test_runtime_code_does_not_import_cbz_module(self):
        references = []
        for directory in (Path("src"), Path("tests")):
            for path in directory.rglob("*.py"):
                if path == Path("tests/test_project_guardrails.py"):
                    continue
                source = path.read_text(encoding="utf-8")
                if "pdf_to_cbz_lossless" in source:
                    references.append(str(path))

        self.assertEqual([], references)

    def test_project_exposes_generic_source_converter_command(self):
        pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('manga-to-epub = "manga_pdf_to_epub.cli.pdf_to_epub_lossless:main"', pyproject)
        self.assertIn('pdf-to-epub-lossless = "manga_pdf_to_epub.cli.pdf_to_epub_lossless:main"', pyproject)

    def test_smoke_uses_python_scripts_dir_for_console_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fake_bin = tmp_path / "bin"
            fake_bin.mkdir()
            fake_python = fake_bin / "python"
            fake_scripts = tmp_path / "python-scripts"
            fake_scripts.mkdir()
            fake_python.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"-c\" ]; then\n"
                "  printf '%s\\n' \"$FAKE_PYTHON_SCRIPTS\"\n"
                "fi\n",
                encoding="utf-8",
            )
            fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
            env["FAKE_PYTHON_SCRIPTS"] = str(fake_scripts)

            result = subprocess.run(
                ["make", "-n", "smoke", "PYTHON=python"],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )

        self.assertNotIn("./manga-to-epub", result.stdout)
        self.assertNotIn("./pdf-to-epub-lossless", result.stdout)
        self.assertIn(f'"{fake_scripts}/manga-to-epub" --help', result.stdout)
        self.assertIn(f'"{fake_scripts}/pdf-to-epub-lossless" --help', result.stdout)


if __name__ == "__main__":
    unittest.main()
