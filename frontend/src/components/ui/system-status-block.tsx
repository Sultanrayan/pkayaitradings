"use client";

import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  ChevronDown,
  ChevronUp,
  Circle,
  AlertTriangle,
  CheckCircle,
} from "lucide-react";

const SERVICES = [
  {
    name: "API",
    status: "operational",
    lastIncident: { date: "2026-09-19", desc: "Cloudflare verification enabled." },
  },
  {
    name: "Analysis engine",
    status: "operational",
    lastIncident: { date: "2026-09-20", desc: "Deploy window, brief restart." },
  },
  { name: "Market data", status: "operational", lastIncident: null },
  {
    name: "Payments",
    status: "operational",
    lastIncident: { date: "2026-09-21", desc: "KHQR plan upgrades went live." },
  },
];

const INCIDENTS = [
  {
    service: "Payments",
    date: "2026-09-21",
    desc: "KHQR plan upgrades went live. No downtime observed.",
  },
  {
    service: "Analysis engine",
    date: "2026-09-20",
    desc: "Brief restart while shipping the intelligence layer.",
  },
  {
    service: "API",
    date: "2026-09-19",
    desc: "Managed Challenge added to the public website.",
  },
];

// Mock uptime history: 1 = up (green), 0 = incident (red)
const UPTIME_HISTORY: Record<string, number[]> = {
  API: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1],
  "Analysis engine": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1],
  "Market data": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
  Payments: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1],
};

function UptimeBar({ history }: { history: number[] }) {
  return (
    <div className="mt-1 flex gap-0.5">
      {history.map((value, index) => (
        <div
          key={index}
          className={`h-6 w-1 rounded-sm ${value ? "bg-green-400" : "bg-red-400"}`}
          title={value ? "Up" : "Incident"}
        />
      ))}
    </div>
  );
}

function getStatusIcon(status: string) {
  if (status === "operational") return <CheckCircle className="h-4 w-4 text-green-500" />;
  if (status === "degraded") return <AlertTriangle className="h-4 w-4 text-yellow-500" />;
  if (status === "down") return <Circle className="h-4 w-4 text-red-500" />;
  return <Circle className="h-4 w-4 text-muted-foreground" />;
}

export default function SystemStatusBlock() {
  const [showIncidents, setShowIncidents] = useState(false);

  return (
    <Card className="mx-auto w-full max-w-xl p-2 md:p-4">
      <CardContent className="flex flex-col gap-6 p-6">
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-lg font-semibold">System Status</span>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setShowIncidents((value) => !value)}
              aria-label={showIncidents ? "Hide incident history" : "Show incident history"}
            >
              {showIncidents ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              <span className="text-xs">{showIncidents ? "Hide" : "Incident History"}</span>
            </Button>
          </div>
          <div className="flex flex-col gap-3">
            {SERVICES.map((service) => (
              <div key={service.name} className="flex flex-col gap-1">
                <div className="flex flex-wrap items-center gap-4">
                  {getStatusIcon(service.status)}
                  <span className="font-medium">{service.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {service.status.charAt(0).toUpperCase() + service.status.slice(1)}
                  </span>
                  {service.lastIncident && (
                    <span className="ml-auto text-xs text-muted-foreground">
                      Last: {service.lastIncident.date}
                    </span>
                  )}
                </div>
                <UptimeBar history={UPTIME_HISTORY[service.name] || []} />
              </div>
            ))}
          </div>
        </div>
        {showIncidents && (
          <div className="mt-2 flex flex-col gap-2 rounded-lg bg-accent p-4">
            <span className="mb-2 text-sm font-semibold">Incident History</span>
            {INCIDENTS.map((incident, index) => (
              <div
                key={index}
                className="flex flex-col gap-1 border-b border-muted-foreground/10 pb-2 last:border-b-0 last:pb-0"
              >
                <span className="text-xs font-medium">
                  {incident.service} - {incident.date}
                </span>
                <span className="text-xs text-muted-foreground">{incident.desc}</span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}