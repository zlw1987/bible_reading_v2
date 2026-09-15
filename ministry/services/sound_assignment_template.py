"""Private raw-byte source for the supported Sound import workbook template."""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
import os
import stat

from django.conf import settings

from .worship_xlsx_preview import EXPECTED_REAL_WORKBOOK_SHA256


DOWNLOAD_FILENAME = "SVCA_2026_Sound_Import_Template.xlsx"
DOWNLOAD_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
_HASH_CHUNK_SIZE = 64 * 1024


class SoundAssignmentTemplateErrorCode(StrEnum):
    UNCONFIGURED = "unconfigured"
    UNAVAILABLE = "unavailable"
    NOT_REGULAR_FILE = "not_regular_file"
    SHA256_MISMATCH = "sha256_mismatch"


class SoundAssignmentTemplateUnavailable(OSError):
    """The configured private template cannot be served safely."""

    def __init__(self, code):
        self.code = SoundAssignmentTemplateErrorCode(code)
        super().__init__(self.code.value)


def open_verified_sound_assignment_template():
    """Open, hash, rewind, and return the unchanged private workbook stream."""

    configured_path = getattr(
        settings, "SOUND_ASSIGNMENT_IMPORT_TEMPLATE_PATH", ""
    )
    try:
        source_path = os.fspath(configured_path)
    except TypeError as exc:
        raise SoundAssignmentTemplateUnavailable(
            SoundAssignmentTemplateErrorCode.UNCONFIGURED
        ) from exc
    if not isinstance(source_path, str) or not source_path.strip():
        raise SoundAssignmentTemplateUnavailable(
            SoundAssignmentTemplateErrorCode.UNCONFIGURED
        )

    try:
        source = open(source_path, "rb")
    except (OSError, ValueError) as exc:
        raise SoundAssignmentTemplateUnavailable(
            SoundAssignmentTemplateErrorCode.UNAVAILABLE
        ) from exc

    try:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise SoundAssignmentTemplateUnavailable(
                SoundAssignmentTemplateErrorCode.NOT_REGULAR_FILE
            )
        digest = sha256()
        while chunk := source.read(_HASH_CHUNK_SIZE):
            digest.update(chunk)
        if digest.hexdigest().upper() != EXPECTED_REAL_WORKBOOK_SHA256:
            raise SoundAssignmentTemplateUnavailable(
                SoundAssignmentTemplateErrorCode.SHA256_MISMATCH
            )
        source.seek(0)
        return source
    except SoundAssignmentTemplateUnavailable:
        source.close()
        raise
    except (OSError, ValueError) as exc:
        source.close()
        raise SoundAssignmentTemplateUnavailable(
            SoundAssignmentTemplateErrorCode.UNAVAILABLE
        ) from exc
