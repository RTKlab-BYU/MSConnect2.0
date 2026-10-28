export type InstanceProfile = "kelly" | "facility" | "ten-dollar-proteome";

const configuredProfile = import.meta.env.VITE_MSConnect_INSTANCE_PROFILE?.trim().toLowerCase();

export const instanceProfile: InstanceProfile =
  configuredProfile === "facility" || configuredProfile === "ten-dollar-proteome"
    ? configuredProfile
    : "kelly";

export const isFacilityProfile = instanceProfile === "facility";
export const instanceLabel =
  instanceProfile === "facility"
    ? "Facility"
    : instanceProfile === "ten-dollar-proteome"
      ? "$10Proteome"
      : "Kelly Lab";
