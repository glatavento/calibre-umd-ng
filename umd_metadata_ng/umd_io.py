# File: umd_io.py
# Date: 2021/4/30 下午7:52
# Author: glatavento

import datetime
import logging
import struct
import zlib
from collections import namedtuple
from pathlib import Path
from typing import Literal, IO

umd_io_logger = logging.Logger("umd-io", logging.INFO)
stdout_handler = logging.StreamHandler()
stdout_handler.setFormatter(logging.Formatter("%(asctime)s - %(filename)s: %(lineno)d - %(levelname)s - %(message)s",
                                              datefmt="%Y-%m-%d %H:%M:%S %p"))
umd_io_logger.addHandler(stdout_handler)

_BLOCK_TYPE_DICT = {
    0x01: "category",
    0x02: "title",
    0x03: "author",
    0x04: "year",
    0x05: "month",
    0x06: "date",
    0x07: "book_type",
    0x08: "publisher",
    0x09: "retailer",
    0x0b: "full_length",
    0x83: "chapter_offsets",
    0x84: "chapter_titles_and_body",
    0x81: "end_of_body",
    0x82: "cover",
    0x87: "page_offset",
    0x0c: "end_of_file"
}

Chapter = namedtuple("Chapter", "title content")


class UMDFile:
    @staticmethod
    def read_metadata(stream: IO, offset: int = None) -> tuple[dict, int]:
        # offset == None : no offset
        # offset >= 0    : offset
        # offset <  0    : auto detect
        if offset is not None:
            if offset >= 0:
                stream.seek(offset)
            else:
                stream.seek(0)

        metadata = dict()
        # [file header]  #    01                 #    02
        # [89 9B 9A DE] 23 01 00 00 08 01 B1 0C 23 02 00 00 27 BB...
        if stream.read(4) != b"\x89\x9b\x9a\xde":
            raise ValueError("Wrong File Header.")

        while True:
            #             [ # bl_tp]                [ # bl_tp]
            # 89 9B 9A DE [23 01 00] 00 08 01 B1 0C [23 02 00] 00 27 BB...
            # bt: block_type_byte
            splitter, block_type_byte = struct.unpack("<cH", stream.read(3))
            assert splitter == b'#'
            block_type = _BLOCK_TYPE_DICT.get(block_type_byte)
            umd_io_logger.debug(f"block type: {block_type}")
            if block_type_byte == 0x01:
                #              #    01 [   h1 cb    h2]  #    02
                # 89 9B 9A DE 23 01 00 [00 08 01 B1 0C] 23 02 00 00 27 BB...
                # cb: category_byte
                h1, category_byte, h2 = struct.unpack("<hbh", stream.read(5))
                # only support novel!
                metadata["category"] = {0x01: "Novel", "0x02": "Comic"}[category_byte]
                umd_io_logger.debug(f"hi, h2: {h1}, {h2}")
            elif block_type_byte in range(0x02, 0x0a):
                #              # 00 01                 #    02 [b1 le chapters...
                # 89 9B 9A DE 23 01 00 00 08 01 B1 0C 23 02 00 [00 27 BB 90 A7...
                # le: raw_length, length = raw_length - 5
                b1, raw_length = struct.unpack("<bb", stream.read(2))
                content = stream.read(raw_length - 5).decode("utf-16-le")
                metadata[block_type] = content
                umd_io_logger.debug(f"b1: {b1}")
            elif block_type_byte == 0x0b:
                #  #    0b [   h1 full_length]  # 83
                # 23 0b 00 [00 09 52 08 03 00] 23 83...
                h1, full_length = struct.unpack("<hi", stream.read(6))
                metadata["full_length"] = full_length
                umd_io_logger.debug(f"h1: {h1}")
            elif block_type_byte == 0x83:
                #  #    83 [   h1          r1 b1          r2       ch_no ch01_offset ch02_offset ...
                # 23 83 00 [01 09 B0 39 00 00 24 B0 39 00 00 3D 00 00 00 00 00 00 00 36 03 ...
                # ch_no: raw_number_of_chapters, number_of_chapters = (raw_ch_no - 9) / 4
                h1, i1, b1, i2, raw_ch_no = struct.unpack("<hibii", stream.read(15))
                assert i1 == i2
                number_of_chapters = int((raw_ch_no - 9) / 4)
                chapter_offsets = struct.unpack("<" + "i" * number_of_chapters, stream.read(4 * number_of_chapters))
                metadata["chapter_offsets"] = tuple(map(lambda x: int(x / 2), chapter_offsets))
                umd_io_logger.debug(f"h1, i1, b1, i2: {h1}, {i1}, {b1}, {i2}")
            elif block_type_byte == 0x84:
                #  #    84 [   h1          i1 b1          i2 [ raw_tt_len l1 title1 ...
                # 23 84 00 [01 09 02 4C 00 00 24 02 4C 00 00 [B0 01 00 00 10 2C 7B 00 4E 77 53 20 00 BA 4E ...
                # raw_tt_len: raw_length_of_titles, title_length = raw_tt_len - 9
                h1, i1, b1, i2, title_len = struct.unpack("<hibii", stream.read(15))
                assert i1 == i2
                end = stream.tell() + title_len - 9
                content = []
                while stream.tell() < end:
                    ch_title_len = struct.unpack("<b", stream.read(1))[0]
                    # title_bytes |> decode |> append to chapters list
                    content.append(stream.read(ch_title_len).decode("utf-16-le"))
                metadata["chapter_titles"] = content
                umd_io_logger.debug(f"h1, i1, b1, i2: {h1}, {i1}, {b1}, {i2}")
                break  # break the while loop !important
            umd_io_logger.debug(f"{block_type}: {metadata.get(block_type)}")
        metadata["body_offset"] = stream.tell()
        umd_io_logger.info(f"{metadata['title']}: Read metadata success.")
        # only support novel!
        if metadata["category"] != "Novel":
            umd_io_logger.warning("Only support Novel!")
        return metadata, stream.tell()

    @staticmethod
    def read_content(stream: IO, offset: int = None) -> tuple[str, int]:
        # offset == None : no offset
        # offset >= 0    : offset
        # offset <  0    : auto detect
        if offset is not None:
            if offset >= 0:
                stream.seek(offset)
            else:
                _, offset = UMDFile.read_metadata(stream, offset=-1)
                stream.seek(offset)

        content_list = []
        rnd_lst = []
        splitter = stream.read(1)
        while True:
            if splitter == b'#':
                end_type = struct.unpack("<h", stream.read(2))[0]
                umd_io_logger.debug(f"end_type: {end_type}")
                if end_type == 0x81:
                    break
                elif end_type == 0xf1:
                    h, *c = struct.unpack("<h" + 16 * "c", stream.read(18))
                    umd_io_logger.debug(f"h, s: {h}, {c}")
                elif end_type == 0x0a:
                    h, i = struct.unpack("<hi", stream.read(6))
                    umd_io_logger.debug(f"h, i: {i}")
                splitter = stream.read(1)
                continue
            elif splitter == b'$':
                #  $           i raw_blc_len block...
                # 24 91 F1 E1 F4 6D 45 00 00 78 9C 8D BD ...
                # raw_blc_len: raw_block_length, block_length = raw_block_length - 9
                i, raw_block_length = struct.unpack("<ii", stream.read(8))
                umd_io_logger.debug(f"i: {i}")
                rnd_lst.append(i)
                block = stream.read(raw_block_length - 9)
                # block |> decompress |> append to content_list
                content_list.append(zlib.decompress(block))
                splitter = stream.read(1)
        #  #    81 [    h          i1  b          i2 raw_n_block   i_of_blc1   i_of_blc2...
        # 23 81 00 [01 09 13 23 00 00 24 13 23 00 00 25 00 00 00 91 F1 E1 F4 A2 C5 F6 FE...
        # raw_n_block: raw_number_of_blocks, number_of_blocks = (raw_n_block - 9) / 4
        h, i1, b, i2, raw_n_block = struct.unpack("<hibii", stream.read(15))
        number_of_blocks = int((raw_n_block - 9) / 4)
        rnd_lst2 = struct.unpack("<" + "i" * number_of_blocks, stream.read(4 * number_of_blocks))
        assert tuple(rnd_lst) == rnd_lst2
        content = b"".join(content_list).decode("utf-16-le")
        umd_io_logger.info(f"Read chapters success.")
        return content, stream.tell()

    @staticmethod
    def read_cover(stream: IO, offset: int = None) -> tuple[bytes, int]:
        # offset == None : no offset
        # offset >= 0    : offset
        # offset <  0    : auto detect
        if offset is not None:
            if offset >= 0:
                stream.seek(offset)
            else:
                _, offset = UMDFile.read_content(stream, offset=-1)
                stream.seek(offset)

        splitter = stream.read(1)
        if not splitter:
            cover = None
            umd_io_logger.info(f"No cover.")
        else:
            next_type = struct.unpack("<h", stream.read(2))[0]
            if next_type == 0x82:
                b1, b2, b3, i1, b4, i2, raw_cover_length = struct.unpack("<bbbibii", stream.read(16))
                cover = stream.read(raw_cover_length - 9)
                umd_io_logger.info(f"Read cover success.")
            else:
                cover = None
                umd_io_logger.info(f"No cover.")
        return cover, stream.tell()

    def __init__(self,
                 title: str = None,
                 author: str = None,
                 category: Literal["Comic", "Novel"] = None,
                 publish_date: datetime.date = None,
                 publisher: str = None,
                 retailer: str = None,
                 cover: bytes = None,
                 chapters: list[Chapter] = None,
                 **metadata):
        self.title = title
        self.author = author
        self.category = category
        self.publish_date = publish_date
        self.publisher = publisher
        self.retailer = retailer
        self.cover = cover
        self.chapters = chapters
        self.metadata = metadata

    @staticmethod
    def from_stream(stream: IO) -> "UMDFile":
        metadata, offset1 = UMDFile.read_metadata(stream)
        content, offset2 = UMDFile.read_content(stream, offset1)
        cover, _ = UMDFile.read_cover(stream, offset2)
        ch_list = []
        for i, ch_title in enumerate(metadata["chapter_titles"]):
            if i + 1 == len(metadata["chapter_offsets"]):
                ch_content = content[metadata["chapter_offsets"][i]:]
            else:
                ch_content = content[metadata["chapter_offsets"][i]:
                                     metadata["chapter_offsets"][i + 1]]
            ch_list.append(Chapter(ch_title, ch_content))
        return UMDFile(chapters=ch_list, **metadata)

    @staticmethod
    def from_file(fn: Path) -> "UMDFile":
        with open(fn, "rb") as file:
            return UMDFile.from_stream(file)
