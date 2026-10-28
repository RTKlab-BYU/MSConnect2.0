# MSConnect instance profiles

The frontend profile changes visible navigation at build time. It does not set the primary lab/workspace name shown in the header, and it does not provide data isolation by itself. Configure the header name in **Administration → Global settings → Instance identity**. Kelly Lab, the facility, and any future `$10Proteome` installation must continue to use separate deployments, databases, and storage roots.

Set `MSCONNECT_INSTANCE_PROFILE` in the build environment before creating the web image:

- `kelly` (default): Projects, QC, Live status, and Settings; submissions/intake routes redirect to Projects.
- `facility`: Projects, Submissions, QC, Live status, and Settings; operators also see the Intake queue.
- `ten-dollar-proteome`: profile label reserved for the future client workflow; no client portal or submission flow is implemented by this profile yet.

For a facility image, run `MSCONNECT_INSTANCE_PROFILE=facility docker compose build web`. For Kelly, omit the variable or set it to `kelly`. Production release images must be built with the intended profile because the browser bundle is static.

The primary lab/workspace name is stored separately as the public `instance_identity.primary_lab_name` value in deployment settings. Signed-in users receive only that display label; the rest of deployment metadata remains admin-only.
