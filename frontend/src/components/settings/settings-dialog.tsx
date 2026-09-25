"use client";

import { toast } from "sonner";

import { useAuth } from "@/components/auth-provider";
import { SettingsPanels } from "@/components/settings/settings-panels";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { resetProfile } from "@/lib/profile";

/** Centered modal that hosts the settings surface, opened from the user profile. */
export function SettingsDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { logout } = useAuth();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] w-full overflow-y-auto bg-card sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Settings</DialogTitle>
          <DialogDescription>
            Analysis preferences, notifications and data connection.
          </DialogDescription>
        </DialogHeader>
        <SettingsPanels
          onSignOut={() => {
            resetProfile();
            onOpenChange(false);
            toast.success("Signed out");
            logout();
          }}
        />
      </DialogContent>
    </Dialog>
  );
}
