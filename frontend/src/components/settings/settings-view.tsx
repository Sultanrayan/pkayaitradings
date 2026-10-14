"use client";

import { PageHeader } from "@/components/shared/primitives";
import { SettingsPanels } from "@/components/settings/settings-panels";

export function SettingsView() {
  return (
    <div className="mx-auto w-full max-w-3xl space-y-4">
      <PageHeader
        title="User Settings"
        description="Manage your profile, AI analysis preferences, notifications and app experience."
      />
      <SettingsPanels />
    </div>
  );
}
