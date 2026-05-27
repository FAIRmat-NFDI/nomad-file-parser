from .file_parser import FileParser, ArchiveWriter
from .text_parser import TextParser, DataTextParser, Quantity, ParsePattern
from .xml_parser import XMLParser
from .tar_parser import TarParser
from .mapping_parser import MappingParser

UnstructuredTextFileParser = TextParser
Parser = ArchiveWriter
