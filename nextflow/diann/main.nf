nextflow.enable.dsl=2

import groovy.json.JsonSlurper

params.diann_version = null
params.version_catalog = "${projectDir}/versions.json"
params.input = null
params.results_dir = null
params.fasta = null
params.library = null
params.cli_script = null
params.threads = 1

def catalog = new JsonSlurper().parse(file(params.version_catalog))
def selected = catalog.versions[params.diann_version]
if (!selected) error "DIA-NN version '${params.diann_version}' is not in ${params.version_catalog}"
if (!file(selected.executable).canExecute()) error "DIA-NN executable is unavailable: ${selected.executable}"
if (!params.input || !file(params.input).exists()) error "Input file is missing: ${params.input}"
if (!params.results_dir) error 'Required: --results_dir'
if (!params.library && !params.fasta) error 'Provide --library or --fasta'
if (params.fasta && !file(params.fasta).exists()) error "FASTA is missing: ${params.fasta}"
if (params.library && !file(params.library).exists()) error "Spectral library is missing: ${params.library}"

process DIANN_SEARCH {
    tag "DIA-NN ${params.diann_version}"
    publishDir params.results_dir, mode: 'copy', overwrite: true
    conda "${projectDir}/${selected.conda_env}"

    input:
    path raw_file

    output:
    path 'report.parquet'
    path 'diann.log'
    path 'search-library.predicted.speclib', optional: true
    path 'library-build.parquet', optional: true

    script:
    def executable = selected.executable
    def log = "'${executable}'"
    if (params.library) {
        """
        ${log} --f '${raw_file}' --lib '${params.library}' --out report.parquet --matrices --threads ${params.threads} > diann.log 2>&1
        """
    } else {
        if (!params.cli_script || !file(params.cli_script).exists()) {
            error 'FASTA search requires an existing --cli_script implementing the supported two-pass DIA-NN speclib build/search.'
        }
        """
        python '${params.cli_script}' ${log} --f '${raw_file}' --fasta '${params.fasta}' --fasta-search --matrices --out report.parquet --threads ${params.threads} > diann.log 2>&1
        """
    }

    stub:
    """
    touch report.parquet diann.log
    """
}

workflow {
    DIANN_SEARCH(Channel.fromPath(params.input, checkIfExists: true))
}
