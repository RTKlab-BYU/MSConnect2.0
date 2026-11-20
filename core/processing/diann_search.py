"""Run FASTA prediction and quantitative search as separate DIA-NN invocations."""
import subprocess
import sys
from pathlib import Path


def main(argv=None):
    command = list(sys.argv[1:] if argv is None else argv)
    report = Path(command[command.index('--out') + 1])
    library = report.parent / 'search-library.predicted.speclib'
    prediction = [command[0]]
    # First pass predicts a library from FASTA. The second pass quantifies raw
    # input against that library and writes the requested report.
    i = 1
    while i < len(command):
        arg = command[i]
        if arg in {'--f', '--out', '--out-lib', '--lib'}:
            i += 2
            continue
        if arg in {'--matrices', '--individual-reports', '--gen-spec-lib', '--predictor'}:
            i += 1
            continue
        prediction.append(arg)
        i += 1
    # DIA-NN appends ``.predicted.speclib`` to --out-lib; pass a basename so
    # the generated path matches the stable artifact name above.
    prediction.extend(['--gen-spec-lib', '--predictor', '--out-lib', str(library.with_suffix('')),
                       '--out', str(report.parent / 'library-build.parquet')])
    subprocess.run(prediction, check=True)
    if not library.is_file():
        raise RuntimeError(f'DIA-NN did not create predicted library: {library}')
    search = [command[0]]
    i = 1
    while i < len(command):
        arg = command[i]
        if arg in {'--fasta', '--fasta-search', '--gen-spec-lib', '--predictor', '--out-lib'}:
            i += 2 if arg in {'--fasta', '--out-lib'} else 1
            continue
        if arg == '--lib':
            i += 2
            continue
        search.append(arg)
        i += 1
    search.extend(['--lib', str(library)])
    subprocess.run(search, check=True)


if __name__ == '__main__':
    main()
