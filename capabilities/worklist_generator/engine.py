from .scripts.blocker import Blocker
from .scripts.excel_parser import ExcelParser
from .scripts.output import Output


def run_worklist(input_filename, output_dir=None):
    """Generate the MS and LC vendor worklists for one completed workbook.

    The parser and blocker are deliberately the same implementation used by
    the command-line generator.  ``output_dir`` is optional so the engine
    remains useful as a standalone Python API while web requests can isolate
    each run in its own directory.
    """
    parser = ExcelParser(input_filename)
    parsed_for_blocker, parsed_for_output = parser.parse()

    blocker = Blocker(parsed_for_blocker)
    blocked_for_output = blocker.block()

    output = Output(parsed_for_output, blocked_for_output, output_dir=output_dir)
    ms_filename, lc_filename, _filenames, _condition_names, _rep_numbers = output.putout()

    return ms_filename, lc_filename
