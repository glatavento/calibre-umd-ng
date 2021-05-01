# File: __init__.py
# Date: 2021/5/1 上午1:56
# Author: glatavento
__author__ = "glatavento"
__license__ = "GPL v3"
__copyright__ = "2021, glatavento <glatavento@outlook.com>"
__version__ = (0, 1, 1)

import logging
from typing import IO

from calibre.customize import MetadataReaderPlugin
from calibre.ebooks.metadata.book.base import Metadata

from .umd_io import UMDFile

umd_plugin_logger = logging.Logger("umd-metadata-plugin", logging.INFO)
stdout_handler = logging.StreamHandler()
stdout_handler.setFormatter(logging.Formatter("%(asctime)s - %(filename)s: %(lineno)d - %(levelname)s - %(message)s",
                                              datefmt="%Y-%m-%d %H:%M:%S %p"))
umd_plugin_logger.addHandler(stdout_handler)


# noinspection PyAbstractClass
class UmdMetaReader(MetadataReaderPlugin):
    name = "UMD Metadata Reader - Next Generation"
    description = 'Read UMD metadata'
    file_types = {'umd'}
    author = __author__
    version = __version__

    # noinspection PyMethodOverriding
    @staticmethod
    def get_metadata(stream: IO, f_type: str) -> Metadata:
        assert f_type == "umd"
        book = UMDFile.from_stream(stream)
        metadata = Metadata(title=book.title,
                            authors=[book.author])
        metadata.publisher = book.publisher
        metadata.pubdate = book.publish_date
        if book.cover:
            metadata.cover_data = ('jpeg', book.cover)
        return metadata
