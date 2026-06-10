from .file_parser import ArchiveWriter, FileParser
from .mapping_parser import MappingParser
from .tar_parser import TarParser
from .text_parser import DataTextParser, ParsePattern, Quantity, TextParser
from .xml_parser import XMLParser

UnstructuredTextFileParser = TextParser
Parser = ArchiveWriter
