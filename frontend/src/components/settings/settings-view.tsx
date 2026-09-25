"use client";

import { PageHeader } from "@/components/shared/primitives";
import { SettingsPanels } from "@/components/settings/settings-panels";

export function SettingsView() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="User Settings"
        description="Analysis preferences, notifications and appearance."
      />
      <SettingsPanels />
    </div>
  );
}
