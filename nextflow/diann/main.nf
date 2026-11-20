nextflow.enable.dsl=2

params.diann_version = null
params.version_catalog = "${projectDir}/versions.json"
params.input = null
params.inputs_json = null
params.results_dir = null
params.fasta = null
params.library = null
params.cli_script = "/opt/msconnect/diann_search.py"
params.threads = 1
params.job_id = ""
params.diann_options_json = "[]"
params.generate_speclib = false

process DIANN_SEARCH {
    tag "${selected_version} · ${input_paths.size()} input(s)"
    label 'diann'
    cpus params.threads as Integer
    time '72h'
    errorStrategy 'terminate'
    publishDir params.results_dir, mode: 'copy', overwrite: true

    input:
    path raw_files
    val input_paths
    val reference_path
    val reference_type
    val selected_version
    val selected_executable
    val helper_path
    val output_dir
    val thread_count
    val batch_job_id
    val diann_options
    val build_library

    output:
    path 'report.parquet'
    path 'diann.log'
    path 'report.stats.tsv', optional: true
    path 'report.pg_matrix.tsv', optional: true
    path 'report.pr_matrix.tsv', optional: true
    path 'report.protein_description.tsv', optional: true
    path 'search-library.predicted.speclib', optional: true
    path 'library-build.parquet', optional: true
    path 'diann-workflow-manifest.json'

    script:
    def inputArgs = input_paths.collect { "--f '${it.toString().replace("'", "'\\''")}'" }.join(' ')
    def referenceArgs = reference_type == 'library' ? "--lib '${reference_path.toString().replace("'", "'\\''")}'" : "--fasta '${reference_path.toString().replace("'", "'\\''")}' --fasta-search"
    def helper = reference_type == 'fasta' ? "python '${helper_path}' '${selected_executable}'" : "'${selected_executable}'"
    def reserved = ['--f', '--out', '--lib', '--fasta', '--threads', '--fasta-search', '--gen-spec-lib', '--predictor', '--out-lib'] as Set
    def optionTokens = diann_options.collect { it.toString() }
    def valueOptions = ['--f', '--out', '--lib', '--fasta', '--threads', '--out-lib'] as Set
    def extraTokens = []
    optionTokens.eachWithIndex { option, index ->
        if (option in reserved || (index > 0 && optionTokens[index - 1] in valueOptions)) return
        extraTokens << option
    }
    def extraArgs = extraTokens.collect { "'${it.toString().replace("'", "'\\''")}'" }.join(' ')
    def libraryArgs = build_library ? '--gen-spec-lib --predictor --out-lib search-library.predicted.speclib' : ''
    """
    set -euo pipefail
    ${helper} ${inputArgs} ${referenceArgs} ${libraryArgs} ${extraArgs} --out report.parquet --threads ${thread_count} > diann.log 2>&1
    test -s report.parquet
    python - <<'PY'
    import json, os, pathlib, subprocess
    paths = ${groovy.json.JsonOutput.toJson(input_paths)}
    files = [{"path": p, "size_bytes": pathlib.Path(p).stat().st_size} for p in paths]
    manifest = {
        "schema_version": 1,
        "job_id": ${groovy.json.JsonOutput.toJson(batch_job_id)},
        "diann_version": ${groovy.json.JsonOutput.toJson(selected_version)},
        "diann_executable": ${groovy.json.JsonOutput.toJson(selected_executable)},
        "nextflow_version": os.environ.get("NXF_VER", "unknown"),
        "inputs": files,
        "reference_type": ${groovy.json.JsonOutput.toJson(reference_type)},
        "reference_path": ${groovy.json.JsonOutput.toJson(reference_path)},
        "threads": int(${thread_count}),
    }
    pathlib.Path("diann-workflow-manifest.json").write_text(json.dumps(manifest, indent=2) + "\\n")
    PY
    """
}

workflow {
    def catalogFile = file(params.version_catalog)
    if (!catalogFile.exists()) error "DIA-NN version catalog is unavailable: ${catalogFile}"
    def catalog = new groovy.json.JsonSlurper().parse(catalogFile)
    def selected = catalog.versions[params.diann_version]
    if (!selected) error "DIA-NN version '${params.diann_version}' is not approved in ${catalogFile}"
    def executable = file(selected.executable)
    if (!executable.exists() || !executable.canExecute()) error "DIA-NN executable is unavailable: ${executable}"
    if (!params.results_dir) error 'Required: --results_dir'
    if (!params.library && !params.fasta) error 'Provide --library or --fasta'
    if (params.fasta && !file(params.fasta).isFile()) error "FASTA is unavailable: ${params.fasta}"
    if (params.library && !file(params.library).isFile()) error "Spectral library is unavailable: ${params.library}"
    if (!params.cli_script || !file(params.cli_script).isFile()) error "DIA-NN helper is unavailable: ${params.cli_script}"
    if (!params.threads.toString().isInteger()) error '--threads must be a positive integer'
    def threadCount = params.threads.toString().toInteger()
    if (threadCount < 1) error '--threads must be a positive integer'

    def inputs = []
    if (params.inputs_json) {
        def parsed = new groovy.json.JsonSlurper().parseText(params.inputs_json)
        if (!(parsed instanceof List) || parsed.isEmpty()) error '--inputs_json must be a non-empty JSON array of input paths'
        inputs = parsed.collect { file(it.toString()) }
    } else if (params.input) {
        inputs = [file(params.input)]
    } else {
        error 'Provide --input or --inputs_json'
    }
    inputs.each { if (!it.isFile()) error "Input file is unavailable: ${it}" }

    def reference = params.library ?: params.fasta
    def referenceType = params.library ? 'library' : 'fasta'
    def inputPaths = inputs.collect { it.toString() }
    DIANN_SEARCH(
        Channel.value(inputs),
        Channel.value(inputPaths),
        Channel.value(reference.toString()),
        Channel.value(referenceType),
        Channel.value(params.diann_version.toString()),
        Channel.value(executable.toString()),
        Channel.value(file(params.cli_script).toString()),
        Channel.value(file(params.results_dir).toString()),
        Channel.value(threadCount),
        Channel.value(params.job_id.toString()),
        Channel.value(new groovy.json.JsonSlurper().parseText(params.diann_options_json ?: '[]')),
        Channel.value(params.generate_speclib as Boolean)
    )
}
