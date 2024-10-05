#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import hashlib
from io import IOBase
import mimetypes
import os
import random
import string
from typing import IO, Literal, TextIO, TypeVar, Union, cast

CONTENT_TYPE_GENERIC = "application/octet-stream"
FILE_NAME_ALPHABET = string.ascii_lowercase + string.digits


def get_ext_from_content_type(content_type: str) -> str:
    """
    Get file extension from content type.

    :param content_type: content type
    :return: file extension with dot. E.g. `.txt`
    """
    if content_type == "application/json":
        return ".json"
    elif content_type == "text/plain":
        return ".txt"
    elif content_type == CONTENT_TYPE_GENERIC:
        return ".dat"
    else:
        candidate = mimetypes.guess_extension(content_type)
        if candidate is not None:
            return candidate
    return ".dat"


def guess_content_type(file_name: str) -> str:
    """
    Guess content type by given file name.

    :param file_name: name of the file
    :return: content type
    """
    return mimetypes.guess_type(file_name)[0] or CONTENT_TYPE_GENERIC


def get_extension(file_name: str) -> str | None:
    """
    Get file extension from file name.

    :param file_name: file name
    :return: file extension with dot (e.g. `.txt`) or None if file doesn't have extension
    """
    parts = file_name.rsplit(".", 1)
    if len(parts) == 2:
        return "." + parts[1]
    return None


def generate_random_file_name(length: int = 40) -> str:
    """
    Generate random string suitable for a file name.

    It doesn't include extension.
    :param length: length of the string to be generated
    :return: random string
    """
    return "".join(random.choice(FILE_NAME_ALPHABET) for _ in range(length))


def ensure_dir(dir_name: os.PathLike | str) -> None:
    """
    Ensure that given directory exists.

    :param dir_name: name of the directory to be ensured
    """
    os.makedirs(dir_name, exist_ok=True)


def calculate_sha1(input_stream: IO | TextIO | IOBase) -> str:
    """
    Calculate SHA1 of the file.

    :param input_stream: input stream to be processed
    :return: checksum in hex string format
    """
    checksum_fn = hashlib.sha1()
    for chunk in iter(lambda: input_stream.read(4096), b""):
        checksum_fn.update(cast(bytes, chunk))
    return checksum_fn.hexdigest()


def calculate_checksum(input_stream: IO | TextIO | IOBase) -> str:
    """
    Calculate checksum of the file.

    :param input_stream: input stream to be processed
    :return: checksum in hex string format
    """
    return calculate_sha1(input_stream)


TIO = TypeVar("TIO", bound=Union[IO, TextIO])
FModeBinary = Literal["rb", "wb", "ab", "rb+", "wb+", "ab+", "xb", "xb+"]
FModeText = Literal["r", "w", "a", "r+", "w+", "a+", "x", "x+"]
