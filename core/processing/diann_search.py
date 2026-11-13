"""Run FASTA prediction and quantitative search as separate DIA-NN invocations."""
import subprocess
import sys
from pathlib import Path


def main(argv=None):
    command = list(sys.argv[1:] if argv is None else argv)
    report = Path(command[command.index('--out') + 1])
    library = report.parent / 'search-library.predicted.speclib'
    prediction = [command[0]]
    # Retain digestion/modification and resource settings, omit raw inputs and
    # report-only switches. The second invocation searches the predicted library.
    i = 1
    while i < len(command):
        arg = command[i]
        if arg in {'--f', '--out', '--out-lib'}:
            i += 2
            continue
        if arg in {'--matrices', '--individual-reports', '--gen-spec-lib', '--predictor'}:
            i += 1
            continue
        prediction.append(arg)
        i += 1
    prediction.extend(['--gen-spec-lib', '--predictor', '--out-lib', str(report.parent / 'search-library.speclib'),
                       '--out', str(report.parent / 'library-build.parquet')])
    subprocess.run(prediction, check=True)
    if not library.is_file():
        raise RuntimeError(f'DIA-NN did not create predicted library: {library}')
    search = [arg for arg in command if arg not in {'--fasta-search', '--gen-spec-lib', '--predictor'}]
    search.extend(['--lib', str(library)])
    subprocess.run(search, check=True)


if __name__ == '__main__':
    main()
