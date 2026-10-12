"""Check safe patch boundaries and a runtime archive without repo imports."""
import ast
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from pypdf import PdfReader
from tools.build_minimal import build, FILES
from tools.patch_turnin import COMMANDS, patched_source


def command_expression(shape):
    import re
    parts = re.split(r"(\{(?:user_dir|server_dir|course)\})", shape)
    symbols = {"{user_dir}": "user_dir", "{server_dir}": "server_dir", "{course}": "class_info[0]"}
    return " + ".join(symbols.get(part, repr(part)) for part in parts if part)


def skeleton():
    # Synthetic function: this is not a copy of the school's original program.
    lines = ["def STD_INFO(class_info, user_dir):", "    CHECK_DUE(class_info[2:4])",
             "    name = input('학생 확인')", "    server_dir = target_for(class_info, name)",
             "    if not os.path.exists(server_dir):", "        os.mkdir(server_dir)", "    else:",
             "        cmd = " + command_expression("rm -rf {server_dir}/*"),
             "        cmd_out = subprocess.getoutput(cmd)"]
    for command in COMMANDS:
        lines += ["    cmd = " + command_expression(command), "    cmd_out = subprocess.getoutput(cmd)"]
    lines += ["    print('성공적으로 제출하였습니다.')", "", "def COURSE_SELECTION():", "    return 'synthetic'", ""]
    return chr(10).join(lines)


class PatchToolsTests(unittest.TestCase):
    def test_patch_only_replaces_known_storage(self):
        original = skeleton()
        patched = patched_source(original)
        ast.parse(patched, feature_version=(3, 8))
        self.assertIn("submit_listing(user_dir, server_dir, class_info[0], name)", patched)
        self.assertIn("sys.exit(1)", patched)
        self.assertEqual(patched.split("    if not os.path.exists")[0].split("    try:")[0],
                         original.split("    if not os.path.exists")[0])
        self.assertEqual(patched.split("    print('성공적으로")[1], original.split("    print('성공적으로")[1])
        self.assertNotIn("enscript", patched)

    def test_patch_refuses_extra_assignment_nested_call_and_changed_command(self):
        original = skeleton()
        variants = [original.replace("    print('성공적으로", "    audit = notify_admin()\n    print('성공적으로"),
                    original.replace("        os.mkdir(server_dir)", "        os.mkdir(server_dir)\n        notify_admin()"),
                    original.replace("--word-wrap", "--word-wrap --extra"),
                    original.replace("subprocess.getoutput(cmd)", "run_something_else(cmd)", 1),
                    original.replace("    cmd_out = subprocess.getoutput(cmd)\n    print('성공적으로 제출하였습니다.')",
                                     "    cmd_out = subprocess.getoutput(cmd); print('성공적으로 제출하였습니다.'); notify_admin()")]
        for text in variants:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    patched_source(text)

    def test_cli_refuses_overwriting_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "original"
            path.write_text(skeleton(), encoding="utf-8")
            tool = Path(__file__).resolve().parent.parent / "tools/patch_turnin.py"
            result = subprocess.run([sys.executable, str(tool), str(path), "--output", str(path)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(path.read_text(encoding="utf-8"), skeleton())

    def test_bundle_runs_outside_repository_and_preserves_pdf_on_bad_utf8(self):
        with tempfile.TemporaryDirectory(prefix="turnin-bundle-test-") as temporary:
            root = Path(temporary)
            archive = build(root / "minimal.zip")
            runtime = root / "runtime"
            with zipfile.ZipFile(archive) as zipped:
                self.assertEqual(set(zipped.namelist()), set(FILES))
                zipped.extractall(runtime)
            source, target = root / "한글 과제", root / "제출함"
            source.mkdir()
            raw = '// 한글 주석 검사\r\nint main() { return 0; }\r\n'.encode('utf-8')
            input_file = source / "공백 한글.c"
            input_file.write_bytes(raw)
            runner = ("import json, pathlib, sys; sys.path.insert(0, sys.argv[1]); "
                      "import turnin_demo.integration as m; "
                      "p=m.submit_listing(sys.argv[2],sys.argv[3],'한글 과목','demo-student'); "
                      "print(json.dumps({'module':m.__file__,'pdf':str(p)}))")
            args = [sys.executable, "-c", runner, str(runtime), str(source), str(target)]
            result = subprocess.run(args, cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads(result.stdout)
            self.assertIn(runtime, Path(record["module"]).parents)
            pdf = Path(record["pdf"])
            self.assertIn("한글 주석 검사", PdfReader(pdf).pages[0].extract_text())
            self.assertEqual((target / input_file.name).read_bytes(), raw)
            before = pdf.read_bytes()
            input_file.write_bytes(b"invalid \xff\n")
            failed = subprocess.run(args, cwd=root, capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(pdf.read_bytes(), before)
            self.assertEqual((target / input_file.name).read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
