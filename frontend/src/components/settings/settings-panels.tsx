"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  Bell,
  Bot,
  BrainCircuit,
  ChevronRight,
  Database,
  Globe,
  LayoutGrid,
  LineChart,
  LogOut,
  Palette,
  Trash2,
  User,
} from "lucide-react";
import { cn } from "cn";

import { useMarketContext } from "@/components/symbol-provider";
import { Field, FieldGrid, SettingRow, SettingsSection, ToggleRow } from "@/components/settings/setting-primitives";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { FlipButton } from "@/components/ui/flip-button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { useProfile } from "@/hooks/use-profile";
import { useSettings } from "@/hooks/use-settings";
import { MARKET_TIMEFRAMES } from "@/lib/constants";
import { profileInitials, saveProfile, type Profile } from "@/lib/profile";
import {
  AI_FOCUS_OPTIONS,
  ANALYSIS_DETAILS,
  ANALYSIS_TYPES,
  CHART_TYPES,
  DENSITY_OPTIONS,
  EXPLANATION_STYLES,
  THEME_OPTIONS,
  clearLocalSettings,
  saveSettings,
  type Settings,
} from "@/lib/settings";

/** BTCUSD → BTC/USD for display. */
function marketLabel(symbol: string): string {
  const value = symbol.toUpperCase();
  if (value.length === 6) return `${value.slice(0, 3)}/${value.slice(3)}`;
  return value;
}

function SettingsSelect({
  value,
  onValueChange,
  options,
  id,
  className,
  disabledOptions,
}: {
  value: string;
  onValueChange: (value: string) => void;
  options: ReadonlyArray<{ value: string; label: string }>;
  id?: string;
  className?: string;
  disabledOptions?: readonly string[];
}) {
  return (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger id={id} size="sm" className={cn("h-8", className)}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem
            key={option.value}
            value={option.value}
            disabled={disabledOptions?.includes(option.value)}
          >
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/**
 * The full settings surface: profile, AI analysis preferences, AI display,
 * chart preferences, notifications, channels, do-not-disturb, appearance,
 * language, AI behaviour and privacy.
 *
 * Everything is analytical — there are no trading-account, balance or
 * execution controls anywhere on this page.
 */
export function SettingsPanels({ onSignOut }: { onSignOut?: () => void }) {
  const { symbols } = useMarketContext();
  const profile = useProfile();
  const settings = useSettings();
  const router = useRouter();

  const [draft, setDraft] = useState<Profile>(profile);
  const [form, setForm] = useState<Settings>(settings);
  const [saved, setSaved] = useState(false);
  const [profileSaved, setProfileSaved] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);
  const avatarInputRef = useRef<HTMLInputElement | null>(null);

  const set = <K extends keyof Settings>(key: K, value: Settings[K]) =>
    setForm((previous) => ({ ...previous, [key]: value }));

  const marketOptions = symbols.length
    ? symbols.map((symbol) => ({ value: symbol, label: marketLabel(symbol) }))
    : [{ value: form.defaultSymbol, label: marketLabel(form.defaultSymbol) }];

  const toggleFocus = (key: string) =>
    setForm((previous) => ({
      ...previous,
      aiFocus: previous.aiFocus.includes(key)
        ? previous.aiFocus.filter((item) => item !== key)
        : [...previous.aiFocus, key],
    }));

  const saveProfileDraft = () => {
    const next: Profile = {
      ...draft,
      name: draft.name.trim() || draft.name,
      email: draft.email.trim(),
      username: draft.username.trim(),
    };
    saveProfile(next);
    setDraft(next);
    setProfileSaved(true);
    toast.success("Profile updated");
    window.setTimeout(() => setProfileSaved(false), 2000);
  };

  const save = () => {
    saveProfileDraft();
    saveSettings(form);
    setSaved(true);
    toast.success("Settings saved successfully.");
    window.setTimeout(() => setSaved(false), 2000);
  };

  const clearData = () => {
    clearLocalSettings();
    setForm(settings);
    setClearOpen(false);
    toast.success("Local data cleared");
  };

  const signOut = () => {
    onSignOut?.();
    router.push("/login");
  };

  return (
    <div className="space-y-3">
      {/* PROFILE */}
      <SettingsSection
        icon={<User className="size-4" />}
        title="Profile"
        description="Manage your account information and profile details."
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
          <div className="flex items-center gap-3 sm:w-48">
            <Avatar className="size-14">
              {draft.avatarUrl ? <AvatarImage src={draft.avatarUrl} alt={draft.name} /> : null}
              <AvatarFallback className="bg-accent">
                {profileInitials(draft.name)}
              </AvatarFallback>
            </Avatar>
            <div className="space-y-1.5">
              <Button
                variant="outline"
                size="sm"
                onClick={() => avatarInputRef.current?.click()}
              >
                Change avatar
              </Button>
              <input
                ref={avatarInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (!file) return;
                  const reader = new FileReader();
                  reader.onload = () =>
                    setDraft((previous) => ({
                      ...previous,
                      avatarUrl: typeof reader.result === "string" ? reader.result : undefined,
                    }));
                  reader.readAsDataURL(file);
                }}
              />
              {draft.avatarUrl ? (
                <button
                  type="button"
                  onClick={() => setDraft((previous) => ({ ...previous, avatarUrl: undefined }))}
                  className="text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                >
                  Remove
                </button>
              ) : null}
            </div>
          </div>

          <div className="min-w-0 flex-1 space-y-3">
            <FieldGrid>
              <Field label="Display Name">
                <Input
                  value={draft.name}
                  onChange={(event) =>
                    setDraft((previous) => ({ ...previous, name: event.target.value }))
                  }
                />
              </Field>
              <Field label="Email">
                <Input
                  type="email"
                  value={draft.email}
                  onChange={(event) =>
                    setDraft((previous) => ({ ...previous, email: event.target.value }))
                  }
                />
              </Field>
              <Field label="Username">
                <Input
                  value={draft.username}
                  onChange={(event) =>
                    setDraft((previous) => ({ ...previous, username: event.target.value }))
                  }
                />
              </Field>
              <Field label="Avatar URL">
                <Input
                  value={draft.avatarUrl ?? ""}
                  placeholder="https://…"
                  onChange={(event) =>
                    setDraft((previous) => ({ ...previous, avatarUrl: event.target.value }))
                  }
                />
              </Field>
            </FieldGrid>
            <FlipButton
              size="sm"
              className="w-auto"
              text1="Updated"
              text2="Save Changes"
              onClick={saveProfileDraft}
              flipped={profileSaved}
              ariaLabel="Save profile changes"
            />
          </div>
        </div>

        {/* Billing lives here rather than in the profile dropdown, so the account
            controls and the plan that meters them read as one place. */}
        <SettingRow
          label="Subscriptions"
          description="Your current plan, usage against both caps, and plan changes."
        >
          <Button asChild variant="outline" size="sm" className="gap-1.5">
            <Link href="/subscriptions">
              Manage
              <ChevronRight className="size-3.5" />
            </Link>
          </Button>
        </SettingRow>
      </SettingsSection>

      {/* AI ANALYSIS PREFERENCES */}
      <SettingsSection
        icon={<BrainCircuit className="size-4" />}
        title="AI Analysis Preferences"
        description="Customize how AI market analysis is displayed across the app."
      >
        <FieldGrid>
          <Field label="Default Market">
            <SettingsSelect
              value={form.defaultSymbol}
              onValueChange={(value) => set("defaultSymbol", value)}
              options={marketOptions}
            />
          </Field>
          <Field label="Default Timeframe">
            <SettingsSelect
              value={form.defaultTimeframe}
              onValueChange={(value) => set("defaultTimeframe", value as Settings["defaultTimeframe"])}
              options={MARKET_TIMEFRAMES.map((item) => ({
                value: item.value,
                label: item.label,
              }))}
            />
          </Field>
        </FieldGrid>
        <SettingRow label="Analysis Type">
          <SettingsSelect
            value={form.defaultAnalysisType}
            onValueChange={(value) => set("defaultAnalysisType", value)}
            options={ANALYSIS_TYPES.map((item) => ({ value: item, label: item }))}
            className="w-56"
          />
        </SettingRow>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs">Minimum AI confidence</span>
            <span className="tabular text-xs font-medium text-muted-foreground">
              {Math.round(form.minConfidence * 100)}%
            </span>
          </div>
          <Slider
            value={[form.minConfidence * 100]}
            max={100}
            step={5}
            onValueChange={(value) => set("minConfidence", (value[0] ?? 65) / 100)}
          />
          <p className="text-[11px] text-muted-foreground">
            Lower-confidence analysis will be de-emphasized in the analysis feed.
          </p>
        </div>
      </SettingsSection>

      {/* AI DISPLAY */}
      <SettingsSection
        icon={<LayoutGrid className="size-4" />}
        title="AI Display"
        description="Choose which analysis information appears on the dashboard and in the feed."
      >
        <ToggleRow
          label="Show AI explanations"
          checked={form.showExplanations}
          onCheckedChange={(value) => set("showExplanations", value)}
        />
        <ToggleRow
          label="Show confidence breakdown"
          checked={form.showConfidenceBreakdown}
          onCheckedChange={(value) => set("showConfidenceBreakdown", value)}
        />
        <ToggleRow
          label="Show technical indicators"
          checked={form.showIndicators}
          onCheckedChange={(value) => set("showIndicators", value)}
        />
        <ToggleRow
          label="Show support & resistance"
          checked={form.showLevels}
          onCheckedChange={(value) => set("showLevels", value)}
        />
        <ToggleRow
          label="Show multi-timeframe analysis"
          checked={form.showMultiTimeframe}
          onCheckedChange={(value) => set("showMultiTimeframe", value)}
        />
        <ToggleRow
          label="Show AI reasoning"
          checked={form.showReasoning}
          onCheckedChange={(value) => set("showReasoning", value)}
        />
      </SettingsSection>

      {/* CHART PREFERENCES */}
      <SettingsSection
        icon={<LineChart className="size-4" />}
        title="Chart Preferences"
        description="Chart defaults inherit your default timeframe."
      >
        <SettingRow label="Chart type">
          <SettingsSelect
            value={form.chartType}
            onValueChange={(value) => set("chartType", value as Settings["chartType"])}
            options={CHART_TYPES}
            className="w-40"
          />
        </SettingRow>
        <ToggleRow
          label="Show Volume"
          checked={form.chartVolume}
          onCheckedChange={(value) => set("chartVolume", value)}
        />
        <ToggleRow
          label="Show EMA"
          checked={form.chartEma}
          onCheckedChange={(value) => set("chartEma", value)}
        />
        <ToggleRow
          label="Show RSI"
          checked={form.chartRsi}
          onCheckedChange={(value) => set("chartRsi", value)}
        />
        <ToggleRow
          label="Show MACD"
          checked={form.chartMacd}
          onCheckedChange={(value) => set("chartMacd", value)}
        />
        <ToggleRow
          label="Support / Resistance"
          checked={form.chartLevels}
          onCheckedChange={(value) => set("chartLevels", value)}
        />
        <ToggleRow
          label="Auto refresh market data"
          checked={form.chartAutoRefresh}
          onCheckedChange={(value) => set("chartAutoRefresh", value)}
        />
      </SettingsSection>

      {/* NOTIFICATION SETTINGS */}
      <SettingsSection
        icon={<Bell className="size-4" />}
        title="Notification Settings"
        description="Choose how you want to receive AI market analysis updates."
      >
        <ToggleRow
          label="AI Analysis Alerts"
          checked={form.notifyAnalysis}
          onCheckedChange={(value) => set("notifyAnalysis", value)}
        />
        <ToggleRow
          label="High Confidence Analysis"
          checked={form.notifyHighConfidence}
          onCheckedChange={(value) => set("notifyHighConfidence", value)}
        />
        <ToggleRow
          label="Market Trend Change"
          checked={form.notifyTrendChange}
          onCheckedChange={(value) => set("notifyTrendChange", value)}
        />
        <ToggleRow
          label="Important Market Event"
          checked={form.notifyMarketEvent}
          onCheckedChange={(value) => set("notifyMarketEvent", value)}
        />
        <ToggleRow
          label="News & Sentiment Updates"
          checked={form.notifyNewsSentiment}
          onCheckedChange={(value) => set("notifyNewsSentiment", value)}
        />
        <ToggleRow
          label="Daily Market Summary"
          checked={form.notifyDailySummary}
          onCheckedChange={(value) => set("notifyDailySummary", value)}
        />
        <ToggleRow
          label="Weekly AI Market Report"
          checked={form.notifyWeeklyReport}
          onCheckedChange={(value) => set("notifyWeeklyReport", value)}
        />
      </SettingsSection>

      {/* NOTIFICATION CHANNELS */}
      <SettingsSection
        icon={<Globe className="size-4" />}
        title="Notification Channels"
        description="Where analysis updates are delivered."
      >
        <ToggleRow
          label="Email"
          checked={form.channelEmail}
          onCheckedChange={(value) => set("channelEmail", value)}
        />
        <SettingRow
          label="Telegram"
          description={
            form.channelTelegram
              ? "Telegram delivery is enabled."
              : "Connect a Telegram bot to enable delivery."
          }
        >
          {form.channelTelegram ? (
            <FlipButton
              size="sm"
              className="w-auto"
              text1="Disconnect"
              text2="Connected"
              onClick={() => set("channelTelegram", false)}
              ariaLabel="Disconnect Telegram"
            />
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={() => set("channelTelegram", true)}
            >
              Connect Telegram
            </Button>
          )}
        </SettingRow>
        <ToggleRow
          label="Push Notifications"
          checked={form.channelPush}
          onCheckedChange={(value) => set("channelPush", value)}
        />
        <ToggleRow
          label="In-App Notifications"
          checked={form.channelInApp}
          onCheckedChange={(value) => set("channelInApp", value)}
        />
      </SettingsSection>

      {/* DO NOT DISTURB */}
      <SettingsSection
        icon={<Bell className="size-4" />}
        title="Do Not Disturb"
        description="Pause non-critical notifications during your selected hours."
      >
        <ToggleRow
          label="Enable"
          checked={form.dndEnabled}
          onCheckedChange={(value) => set("dndEnabled", value)}
        />
        {form.dndEnabled ? (
          <FieldGrid>
            <Field label="Start">
              <Input
                type="time"
                value={form.dndStart}
                onChange={(event) => set("dndStart", event.target.value)}
              />
            </Field>
            <Field label="End">
              <Input
                type="time"
                value={form.dndEnd}
                onChange={(event) => set("dndEnd", event.target.value)}
              />
            </Field>
          </FieldGrid>
        ) : null}
      </SettingsSection>

      {/* APPEARANCE */}
      <SettingsSection
        icon={<Palette className="size-4" />}
        title="Appearance"
        description="Theme, density and motion."
      >
        <SettingRow
          label="Theme"
          description="The interface ships dark-only; light and system themes are not available yet."
        >
          <SettingsSelect
            value={form.theme}
            onValueChange={(value) => set("theme", value)}
            options={THEME_OPTIONS}
            disabledOptions={["light", "system"]}
            className="w-32"
          />
        </SettingRow>
        <SettingRow label="Density">
          <SettingsSelect
            value={form.density}
            onValueChange={(value) => set("density", value)}
            options={DENSITY_OPTIONS}
            className="w-40"
          />
        </SettingRow>
        <ToggleRow
          label="Animations"
          checked={form.animations}
          onCheckedChange={(value) => set("animations", value)}
        />
      </SettingsSection>

      {/* LANGUAGE */}
      <SettingsSection
        icon={<Globe className="size-4" />}
        title="Language"
        description="Interface language."
      >
        <SettingRow label="Language">
          <SettingsSelect
            value={form.language}
            onValueChange={(value) => set("language", value)}
            options={[{ value: "en", label: "English" }]}
            className="w-40"
          />
        </SettingRow>
      </SettingsSection>

      {/* AI PREFERENCES */}
      <SettingsSection
        icon={<Bot className="size-4" />}
        title="AI Preferences"
        description="How AI analysis is presented to you."
      >
        <SettingRow label="AI Explanation Style">
          <SettingsSelect
            value={form.explanationStyle}
            onValueChange={(value) => set("explanationStyle", value)}
            options={EXPLANATION_STYLES}
            className="w-36"
          />
        </SettingRow>
        <SettingRow label="AI Analysis Detail">
          <SettingsSelect
            value={form.analysisDetail}
            onValueChange={(value) => set("analysisDetail", value)}
            options={ANALYSIS_DETAILS}
            className="w-36"
          />
        </SettingRow>
        <div className="space-y-2">
          <span className="text-xs">Preferred AI Focus</span>
          <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
            {AI_FOCUS_OPTIONS.map((option) => {
              const checked = form.aiFocus.includes(option.key);
              return (
                <label
                  key={option.key}
                  className={cn(
                    "flex cursor-pointer items-center gap-2 rounded-md border border-border px-2.5 py-1.5 text-xs transition-colors",
                    checked ? "bg-accent/40" : "hover:bg-accent/20",
                  )}
                >
                  <Checkbox
                    checked={checked}
                    onCheckedChange={() => toggleFocus(option.key)}
                  />
                  {option.label}
                </label>
              );
            })}
          </div>
        </div>
      </SettingsSection>

      {/* PRIVACY & DATA */}
      <SettingsSection
        icon={<Database className="size-4" />}
        title="Privacy & Data"
        description="What is stored locally and what is shared."
      >
        <ToggleRow
          label="Save analysis history"
          checked={form.saveHistory}
          onCheckedChange={(value) => set("saveHistory", value)}
        />
        <ToggleRow
          label="Personalize AI responses"
          checked={form.personalizeAi}
          onCheckedChange={(value) => set("personalizeAi", value)}
        />
        <ToggleRow
          label="Save recent searches"
          checked={form.saveSearches}
          onCheckedChange={(value) => set("saveSearches", value)}
        />
        <ToggleRow
          label="Anonymous usage analytics"
          checked={form.anonymousAnalytics}
          onCheckedChange={(value) => set("anonymousAnalytics", value)}
        />
        <div className="border-t border-border pt-3">
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5 text-bear"
            onClick={() => setClearOpen(true)}
          >
            <Trash2 className="size-3.5" />
            Clear Local Data
          </Button>
        </div>
      </SettingsSection>

      {/* Footer */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card/40 px-3 py-3">
        <p className="text-[11px] text-muted-foreground">
          Preferences and profile are stored locally in your browser.
        </p>
        <div className="flex items-center gap-2">
          {onSignOut ? (
            <Button variant="outline" onClick={signOut} className="gap-2">
              <LogOut className="size-4" />
              Sign out
            </Button>
          ) : null}
          <FlipButton
            className="w-auto"
            text1="Saved"
            text2="Save Preferences"
            onClick={save}
            flipped={saved}
            ariaLabel="Save preferences"
          />
        </div>
      </div>

      <Dialog open={clearOpen} onOpenChange={setClearOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Clear local data?</DialogTitle>
            <DialogDescription>
              This removes your saved preferences from this browser. Your profile and
              analysis history stay on the server and can be restored by signing in again.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setClearOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={clearData}>
              Clear data
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
