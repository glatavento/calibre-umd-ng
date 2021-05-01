# File: __init__.py
# Date: 2021/5/1 上午1:56
# Author: glatavento
__author__ = "glatavento"
__license__ = "GPL v3"
__copyright__ = "2021, glatavento <glatavento@outlook.com>"
__version__ = (0, 1, 0)

import logging
import uuid
from pathlib import Path
from typing import IO

from calibre.customize.conversion import InputFormatPlugin
from calibre.ebooks.txt.processor import convert_basic
from calibre.ptempfile import TemporaryDirectory

from .umd_io import UMDFile

umd_plugin_logger = logging.Logger("umd-input-plugin", logging.INFO)
stdout_handler = logging.StreamHandler()
stdout_handler.setFormatter(logging.Formatter("%(asctime)s - %(filename)s: %(lineno)d - %(levelname)s - %(message)s",
                                              datefmt="%Y-%m-%d %H:%M:%S %p"))
umd_plugin_logger.addHandler(stdout_handler)


# noinspection PyAbstractClass
class UMDInput(InputFormatPlugin):
    name = 'UMD Input - Next Generation'
    description = 'Convert UMD files to OEB'
    file_types = {'umd'}
    author = __author__
    version = __version__

    def initialize(self):
        from calibre.ebooks import BOOK_EXTENSIONS
        if 'umd' not in BOOK_EXTENSIONS:
            BOOK_EXTENSIONS.append('umd')

    def convert(self, stream: IO, options, file_ext, log, accelerators):
        from calibre.ebooks.oeb.base import DirContainer
        from calibre.ebooks.conversion.plumber import create_oebbook
        log.debug("Parsing UMD file...")
        book = UMDFile.from_stream(stream)
        log.debug("Handle meta data ...")
        oeb = create_oebbook(log, None, options, encoding=options.input_encoding, populate=False)
        oeb.metadata.add('title', book.title)
        oeb.metadata.add('creator', book.author, attrib={'role': 'aut'})
        oeb.metadata.add('publisher', book.publisher)
        oeb.metadata.add('identifier', str(uuid.uuid4()), id='uuid_id', scheme='uuid')
        for id_ in oeb.metadata.identifier:
            if 'id' in id_.attrib:
                oeb.uid = oeb.metadata.identifier[0]
                break

        with TemporaryDirectory('_umd2oeb', keep=True) as tmp_dir:
            log.debug('Process TOC ...')
            oeb.container = DirContainer(tmp_dir, log)
            content, cover = book.chapters, book.cover
            if content:
                for i, ch in enumerate(content):
                    ch_title, ch_content = ch.title, ch.content
                    if ch_title is None or ch_content is None:
                        continue
                    ch_content = ch_content.replace("\u2029", "")
                    ch_fn = Path(tmp_dir) / f"ch_{i:04d}.html"
                    ch_fn.write_text(convert_basic(ch_content, title=ch_title))
                    oeb.toc.add(ch_title, ch_fn.name)
                    id_, href = oeb.manifest.generate(id='html', href=ch_fn.name)
                    item = oeb.manifest.add(id_, href, 'text/html')
                    item.html_input_href = ch_fn.name
                    oeb.spine.add(item, True)
            if cover:
                cover_file = Path(tmp_dir) / "cover.jpeg"
                cover_file.write_bytes(cover)
                id_, href = oeb.manifest.generate(id='image', href=cover_file.name)
                oeb.guide.add('cover', 'Cover', href)
        return oeb
