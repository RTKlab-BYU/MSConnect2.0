# MSConnect Roadmap

This document tracks the local plan before the project is pushed to the lab GitHub organization.

## Current MVP Scaffold

- Dockerized Django application with SQLite persistence and nginx reverse proxy.
- Core LIMS/SDMS records for University, Facility, Lab, User roles, Instrument, LC/MS configuration, Project, Experiment, Sample, Run, RawFile, ProcessingPipeline, ProcessingJob, Protein, Peptide, identifications, and quantification values.
- Django admin registration for rapid internal data management.
- Authenticated REST API scaffold for core entities.
- Watched-share raw-file importer with checksum-based idempotency and support for files and vendor raw directories.
- CI workflow for linting, Django checks, migration drift detection, tests, and image build.

## Next Additions

1. Access control
   - Enforce lab/project-scoped permissions in the API.
   - Add tests for PI, researcher, collaborator, and admin visibility.

2. Ingestion workflow
   - Add an ingest review screen for discovered files.
   - Parse a filename or sidecar metadata convention into run/sample fields.
   - Record import failures as database rows instead of only console output.

3. Results import
   - Add importer commands for common peptide/protein result tables.
   - Validate required columns and preserve source file provenance.
   - Add summary views for run-level IDs and quantification counts.

4. Operational readiness
   - Add a documented SQLite and raw-storage backup/restore command.
   - Add health checks for web, ingest, storage mount availability, and database access.
   - Configure production settings for the facility host name and trusted origins.

5. User experience
   - Build focused screens for projects, experiments, samples, runs, and raw files.
   - Add search/filter views for core records.
   - Add run detail pages that show raw files, processing jobs, and result summaries.

6. Lab GitHub rollout
   - Create the lab repository.
   - Add the GitHub remote.
   - Push the local commit history.
   - Protect the main branch and require CI before merges.

