"use client";

import { useEffect, useState } from "react";
import { Bell, LogOut, Save, SlidersHorizontal, User } from "lucide-react";
import { toast } from "sonner";

import { useMarketContext } from "@/components/symbol-provider";
import { Panel } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { useProfile } from "@/hooks/use-profile";
import { MARKET_TIMEFRAMES } from "@/lib/constants";
import { saveProfile, type Profile } from "@/lib/profile";
import type { ChartTimeframe } from "@/lib/types";

interface Preferences {
  defaultSymbol: string;
  defaultTimeframe: ChartTimeframe;
  confidenceThreshold: number;
  notifyEmail: boolean;
  notifyTelegram: boolean;
  notifyPush: boolean;
  dnd: boolean;
}

const STORAGE_KEY = "pkay.preferences";

/**
 * The full settings surface (profile, preferences, notifications, theme, data).
 *
 * Rendered both by the `/settings` page and inside the centered settings
 * dialog opened from the user profile.
 */
export function SettingsPanels({ onSignOut }: { onSignOut?: () => void }) {
  const { symbols, symbol, setSymbol, timeframe, setTimeframe } = useMarketContext();
  const [preferences, setPreferences] = useState<Preferences>({
    defaultSymbol: symbol,
    defaultTimeframe: timeframe,
    confidenceThreshold: 0.65,
    notifyEmail: false,
    notifyTelegram: false,
    notifyPush: true,
    dnd: false,
  });
  const [saved, setSaved] = useState(false);
  const profile = useProfile();
  const [profileDraft, setProfileDraft] = useState<Profile>(profile);

  const saveProfileDraft = () => {
    saveProfile({ ...profileDraft, name: profileDraft.name.trim() || profile.name });
    toast.success("Profile updated");
  };

  useEffect(() => {
    let active = true;
    void (async () => {
      await Promise.resolve();
      if (!active) return;
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (!stored) return;
      try {
        setPreferences((previous) => ({ ...previous, ...(JSON.parse(stored) as Preferences) }));
      } catch {
        /* ignore malformed storage */
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const save = () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
    setSymbol(preferences.defaultSymbol);
    setTimeframe(preferences.defaultTimeframe);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="space-y-4">
      <div className="space-y-4">
        <Panel
          title={
            <span className="flex items-center gap-2">
              <User className="size-4" /> Profile
            </span>
          }
          description="Your display name and contact email"
          action={
            <Button size="sm" onClick={saveProfileDraft} className="gap-1.5">
              <Save className="size-3.5" />
              Save
            </Button>
          }
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="profile-name">Name</Label>
              <Input
                id="profile-name"
                value={profileDraft.name}
                onChange={(event) =>
                  setProfileDraft((previous) => ({ ...previous, name: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="profile-email">Email</Label>
              <Input
                id="profile-email"
                type="email"
                value={profileDraft.email}
                onChange={(event) =>
                  setProfileDraft((previous) => ({ ...previous, email: event.target.value }))
                }
              />
            </div>
          </div>
        </Panel>

        <Panel
          title={
            <span className="flex items-center gap-2">
              <SlidersHorizontal className="size-4" /> Analysis Preferences
            </span>
          }
          description="Defaults applied across the app"
        >
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Default symbol</Label>
              <Select
                value={preferences.defaultSymbol}
                onValueChange={(value) =>
                  setPreferences((prev) => ({ ...prev, defaultSymbol: value }))
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {symbols.map((item) => (
                    <SelectItem key={item} value={item}>
                      {item}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Default timeframe</Label>
              <Select
                value={preferences.defaultTimeframe}
                onValueChange={(value) =>
                  setPreferences((prev) => ({ ...prev, defaultTimeframe: value as ChartTimeframe }))
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MARKET_TIMEFRAMES.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>
                Confidence threshold — {(preferences.confidenceThreshold * 100).toFixed(0)}%
              </Label>
              <Slider
                value={[preferences.confidenceThreshold * 100]}
                max={100}
                step={5}
                onValueChange={(value) =>
                  setPreferences((prev) => ({
                    ...prev,
                    confidenceThreshold: (value[0] ?? 0) / 100,
                  }))
                }
              />
              <p className="text-[11px] text-muted-foreground">
                Signals below this confidence are de-emphasised in the feed.
              </p>
            </div>
          </div>
        </Panel>

        <Panel
          title={
            <span className="flex items-center gap-2">
              <Bell className="size-4" /> Notification Settings
            </span>
          }
          description="Delivery channels (require backend workers)"
        >
          <div className="space-y-4">
            {[
              { key: "notifyEmail" as const, label: "Email alerts" },
              { key: "notifyTelegram" as const, label: "Telegram bot" },
              { key: "notifyPush" as const, label: "Push notifications" },
              { key: "dnd" as const, label: "Do not disturb" },
            ].map((item) => (
              <div key={item.key} className="flex items-center justify-between">
                <Label className="font-normal">{item.label}</Label>
                <Switch
                  checked={preferences[item.key]}
                  onCheckedChange={(checked) =>
                    setPreferences((prev) => ({ ...prev, [item.key]: checked }))
                  }
                />
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
        <p className="text-[11px] text-muted-foreground">
          Preferences and profile are stored locally in your browser.
        </p>
        <div className="flex items-center gap-2">
          {onSignOut ? (
            <Button variant="outline" onClick={onSignOut} className="gap-2">
              <LogOut className="size-4" />
              Sign out
            </Button>
          ) : null}
          <Button onClick={save} className="gap-2">
            <Save className="size-4" />
            {saved ? "Saved" : "Save preferences"}
          </Button>
        </div>
      </div>
    </div>
  );
}
