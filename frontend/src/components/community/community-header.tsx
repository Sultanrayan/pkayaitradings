"use client";

import { useState } from "react";
import { SearchIcon, UsersIcon } from "lucide-react";

import { PageHeader } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";

export function CommunityHeader({
  memberCount = 12840,
  onSearch,
}: {
  memberCount?: number;
  onSearch: () => void;
}) {
  const [memberCountSafe] = useState(memberCount);
  return (
    <PageHeader
      title={
        <span className="flex items-center gap-2">
          <UsersIcon className="size-5" /> Community
        </span>
      }
      description="Discuss markets, share ideas, and connect with traders."
      actions={
        <div className="flex items-center gap-2">
          <span className="hidden items-center gap-1.5 text-xs text-muted-foreground sm:inline-flex">
            <UsersIcon className="size-3.5" />
            <span className="tabular">{memberCountSafe.toLocaleString()}</span> members
          </span>
          <Button variant="outline" size="sm" className="gap-1.5" onClick={onSearch}>
            <SearchIcon className="size-3.5" />
            Search community
          </Button>
        </div>
      }
    />
  );
}