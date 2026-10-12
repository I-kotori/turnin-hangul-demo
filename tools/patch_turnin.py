#!/usr/bin/env python3
"""Create a patched COPY of a locally supplied turnin; never install or execute it."""
import argparse
import ast
import difflib
from pathlib import Path
import stat


def _shape(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in ("user_dir", "server_dir"):
        return "{" + node.id + "}"
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "class_info":
        index = node.slice.value if isinstance(node.slice, ast.Index) else node.slice
        if isinstance(index, ast.Constant) and index.value == 0:
            return "{course}"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _shape(node.left) + _shape(node.right)
    raise ValueError("알 수 없는 명령 표현식입니다. 수동 검토가 필요합니다.")


COMMANDS = (
    "enscript -2rj --header='[{course}] %n : $n|%W %C|$%/$=' --word-wrap --line-numbers --highlight=cpp --color=1 -o {user_dir}/hw.ps {user_dir}/*.c {user_dir}/*.cpp {user_dir}/*.h ",
    "ps2pdf {user_dir}/hw.ps {user_dir}/hw.pdf",
    "rm -rf {user_dir}/hw.ps ",
    "cp {user_dir}/*.c {user_dir}/*.cpp {user_dir}/*.h {server_dir}",
    "cp {user_dir}/hw.pdf {server_dir}",
    "chmod 700 -R {server_dir}",
)


def _pair(statements, expected):
    if len(statements) != 2:
        return False
    command, result = statements
    if not (isinstance(command, ast.Assign) and len(command.targets) == 1
            and isinstance(command.targets[0], ast.Name) and command.targets[0].id == "cmd"):
        return False
    if _shape(command.value) != expected:
        return False
    return ast.dump(result) == ast.dump(ast.parse("cmd_out = subprocess.getoutput(cmd)").body[0])


def _known_storage(segment):
    first = segment[0]
    if len(segment) != 1 + 2 * len(COMMANDS):
        return False
    expected_test = ast.parse("not os.path.exists(server_dir)", mode="eval").body
    expected_mkdir = ast.parse("os.mkdir(server_dir)").body[0]
    if (ast.dump(first.test) != ast.dump(expected_test)
            or len(first.body) != 1 or ast.dump(first.body[0]) != ast.dump(expected_mkdir)
            or not _pair(first.orelse, "rm -rf {server_dir}/*")):
        return False
    return all(_pair(segment[1 + 2*i:3 + 2*i], expected)
               for i, expected in enumerate(COMMANDS))


def patched_source(text):
    tree = ast.parse(text)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "STD_INFO"]
    if len(functions) != 1:
        raise ValueError("STD_INFO 함수를 하나 찾을 수 있어야 합니다.")
    body = functions[0].body
    starts = [i for i, n in enumerate(body) if isinstance(n, ast.If)
              and isinstance(n.test, ast.UnaryOp) and isinstance(n.test.op, ast.Not)
              and isinstance(n.test.operand, ast.Call)
              and isinstance(n.test.operand.func, ast.Attribute)
              and n.test.operand.func.attr == "exists"
              and len(n.test.operand.args) == 1
              and isinstance(n.test.operand.args[0], ast.Name)
              and n.test.operand.args[0].id == "server_dir"]
    ends = [i for i, n in enumerate(body) if isinstance(n, ast.Expr)
            and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name)
            and n.value.func.id == "print" and n.value.args
            and isinstance(n.value.args[0], ast.Constant)
            and isinstance(n.value.args[0].value, str)
            and "성공적으로 제출하였습니다." in n.value.args[0].value]
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        raise ValueError("알고 있는 저장 구간과 성공 문구를 찾지 못했습니다.")
    segment = body[starts[0]:ends[0]]
    if not _known_storage(segment):
        raise ValueError("알고 있는 저장 골격과 다릅니다. 수동 검토가 필요합니다.")
    lines = text.splitlines(keepends=True)
    first, last = segment[0].lineno - 1, segment[-1].end_lineno
    # AST columns are UTF-8 byte offsets; do not delete another same-line statement.
    suffix = lines[last - 1].encode("utf-8")[segment[-1].end_col_offset:].decode("utf-8").strip()
    if suffix and not suffix.startswith("#"):
        raise ValueError("교체 마지막 줄에 추가 동작이 있습니다. 수동 검토가 필요합니다.")
    indent = lines[first][:len(lines[first]) - len(lines[first].lstrip())]
    replacement = ["try:", "    from turnin_demo.integration import submit_listing",
                   "    submit_listing(user_dir, server_dir, class_info[0], name)",
                   "except Exception as error:", '    print("제출 실패: %s" % error)',
                   "    sys.exit(1)"]
    result = "".join(lines[:first]) + "".join(indent + line + chr(10) for line in replacement)
    result += "".join(lines[last:])
    ast.parse(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--diff", type=Path)
    args = parser.parse_args()
    if args.original.resolve() == args.output.resolve():
        parser.error("원본을 덮어쓸 수 없습니다. 다른 출력 경로를 지정하세요.")
    if args.diff and args.diff.resolve() in (args.original.resolve(), args.output.resolve()):
        parser.error("diff 경로도 원본 및 수정본과 달라야 합니다.")
    try:
        text = args.original.read_text(encoding="utf-8")
        result = patched_source(text)
        outputs = [args.output] + ([args.diff] if args.diff else [])
        if any(path.exists() or path.is_symlink() for path in outputs):
            raise ValueError("출력 파일이 이미 있습니다. 새 경로를 지정하세요.")
        for path in outputs:
            path.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(result)
        args.output.chmod(stat.S_IMODE(args.original.stat().st_mode))
        if args.diff:
            diff = difflib.unified_diff(text.splitlines(keepends=True), result.splitlines(keepends=True),
                                        fromfile="turnin.original", tofile="turnin.patched")
            with args.diff.open("x", encoding="utf-8") as handle:
                handle.writelines(diff)
    except (OSError, ValueError, SyntaxError) as error:
        parser.exit(1, str(error) + chr(10))
    print("수정 사본:", args.output.resolve())


if __name__ == "__main__":
    main()
