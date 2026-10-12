"""Small file-based connection for the existing Linux turnin script."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import shutil
import stat
import tempfile
import warnings

from .pdf import render_pdf


class IntegrationError(RuntimeError):
    """Submission failed; any retained recovery path is included in the message."""


@contextmanager
def _lock(directory):
    # DEPLOY: 이 잠금은 수정된 호출끼리만 적용됩니다. 구버전 혼용과 읽기 동기화는 별도로 검토합니다.
    fd = os.open(str(directory / ".turnin-pdf.lock"),
                 os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise IntegrationError("제출 잠금 파일이 일반 파일이 아닙니다.")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _publish(prepared, destination):
    # DEPLOY: 신규 학생 폴더 생성에는 부모의 쓰기·탐색 권한이 필요합니다.
    # 기존 폴더 재제출에는 학생 폴더 내부의 생성·이동·삭제·chmod 권한을 확인합니다.
    destination.mkdir(mode=0o700, exist_ok=True)
    with _lock(destination):
        previous_mode = stat.S_IMODE(destination.stat().st_mode)
        previous = sorted((p for p in destination.iterdir() if not p.name.startswith(".")),
                          key=lambda p: p.name)
        if any(p.is_symlink() or not p.is_file() for p in previous):
            raise IntegrationError("제출 폴더에 일반 파일이 아닌 항목이 있어 교체를 중단합니다.")
        recovery = Path(tempfile.mkdtemp(prefix=".turnin-recovery-", dir=str(destination)))
        incoming, backup = recovery / "new", recovery / "old"
        incoming.mkdir()
        backup.mkdir()
        saved, installed, retain = [], [], False
        try:
            # Copy and set permissions before moving any previous visible file.
            for path in prepared:
                staged = incoming / path.name
                shutil.copy2(path, staged, follow_symlinks=False)
                # DEPLOY: 기존 700 정책을 유지합니다. 교수자 접근에 필요한 소유권·ACL을 확인합니다.
                # 권한 정책을 바꾸면 아래 destination.chmod(0o700)도 함께 검토합니다.
                staged.chmod(0o700)
            try:
                destination.chmod(0o700)
                for path in previous:
                    os.replace(path, backup / path.name)
                    saved.append(path.name)
                for path in prepared:
                    os.replace(incoming / path.name, destination / path.name)
                    installed.append(path.name)
            except Exception as error:
                try:
                    for name in installed:
                        (destination / name).unlink()
                    for name in saved:
                        os.replace(backup / name, destination / name)
                    destination.chmod(previous_mode)
                except Exception as rollback_error:
                    retain = True
                    raise IntegrationError(
                        "제출 교체 및 복구 실패. 백업을 보존했습니다: %s (%s; %s)"
                        % (recovery, error, rollback_error)) from error
                raise IntegrationError("제출 교체 실패; 이전 제출을 복구했습니다: %s" % error) from error
        finally:
            if not retain:
                try:
                    shutil.rmtree(recovery)
                except OSError as error:
                    warnings.warn("임시 백업 정리 실패: %s (%s)" % (recovery, error))


def submit_listing(source_dir, server_dir, course, submitter):
    """Prepare UTF-8 sources/PDF, then replace visible files in one student folder.

    Source snapshots are used for both PDF and submitted files. Caught publish
    errors restore previous files; rollback errors retain an explicit backup.
    Patched calls coordinate with flock. This is not a crash-atomic directory
    transaction, and legacy callers/readers do not participate in the lock.
    """
    # DEPLOY: course·submitter·server_dir는 기존 제출기의 실제 값을 전달합니다.
    # 개발 검증에서는 호출하는 쪽에서 목적지를 승인된 테스트 폴더로 대체합니다.
    source = Path(source_dir).expanduser().absolute()
    destination = Path(server_dir).expanduser().absolute()
    if source.is_symlink() or not source.is_dir():
        raise IntegrationError("소스 경로는 심볼릭 링크가 아닌 디렉터리여야 합니다.")
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise IntegrationError("제출 경로는 심볼릭 링크가 아닌 디렉터리여야 합니다.")
    a, b = source.resolve(), destination.resolve()
    if a == b or a in b.parents or b in a.parents:
        raise IntegrationError("소스 폴더와 제출 폴더는 서로 포함하지 않는 별도 경로여야 합니다.")
    paths = [p for suffix in (".c", ".cpp", ".h")
             for p in sorted(source.glob("*" + suffix), key=lambda p: p.name)
             if not p.name.startswith(".")]
    if not paths or any(p.is_symlink() or not p.is_file() for p in paths):
        raise IntegrationError("제출할 일반 .c, .cpp, .h 파일이 필요합니다.")
    try:
        # DEPLOY: 입력 폴더에는 임시 사본과 hw.pdf 미리보기를 만들 수 있는 쓰기 권한이 필요합니다.
        with tempfile.TemporaryDirectory(prefix=".turnin-prepare-", dir=str(source)) as temporary:
            working = Path(temporary)
            snapshots = []
            for path in paths:
                snapshot = working / path.name
                shutil.copy2(path, snapshot, follow_symlinks=False)
                snapshots.append(snapshot)
            pdf = working / "hw.pdf"
            render_pdf(snapshots, pdf, course, submitter)
            # Retain the original script's local preview; submit the frozen PDF.
            preview = working / "preview.pdf"
            shutil.copy2(pdf, preview, follow_symlinks=False)
            os.replace(preview, source / "hw.pdf")
            _publish(snapshots + [pdf], destination)
    except IntegrationError:
        raise
    except Exception as error:
        raise IntegrationError("제출 준비 또는 저장 실패: %s" % error) from error
    return destination / "hw.pdf"
