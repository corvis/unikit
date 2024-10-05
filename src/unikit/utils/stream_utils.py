#
#  Copyright 2024 by Dmitry Berezovsky, MIT License
#
import shutil
from typing import IO


def copy_stream(src_stream: IO, target_stream: IO, chunk_size: int = 4096) -> None:
    """
    Copy the contents of one stream to another.

    :param src_stream: the input stream to copy data from
    :param target_stream: the output stream to copy data to
    :param chunk_size: the size of the chunks that data will be read and written in. Defaults to 4096
    :return: None
    """
    shutil.copyfileobj(src_stream, target_stream, length=chunk_size)
