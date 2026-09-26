"use client";

import {
  CreditCardIcon,
  FlameIcon,
  HashIcon,
  UserPlusIcon,
  UserCheckIcon,
} from "lucide-react";
import { cn } from "cn";

import { UserAvatar } from "@/components/community/shared";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatSignedPercent } from "@/lib/format";
import type { TrendingMarket, TrendingTopic } from "@/hooks/use-social";

function SidebarCard({
  title,
  icon,
  children,
}: {
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Card className="ring-border">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          {icon}
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-2 pb-2">{children}</CardContent>
    </Card>
  );
}

export function TrendingMarkets({
  markets,
  onOpenMarket,
}: {
  markets: TrendingMarket[];
  onOpenMarket: (symbol: string) => void;
}) {
  return (
    <SidebarCard title="Trending Markets" icon={<FlameIcon className="size-4 text-gold" />}>
      <div className="divide-y divide-border/70">
        {markets.map((market) => (
          <button
            key={market.symbol}
            type="button"
            onClick={() => onOpenMarket(market.symbol)}
            className="flex w-full items-center gap-2 px-2 py-2 text-left transition-colors hover:bg-accent/40"
          >
            <HashIcon className="size-3.5 text-muted-foreground" />
            <span className="text-xs font-semibold uppercase">{market.symbol}</span>
            <span className="ml-auto flex items-center gap-2">
              <span className={cn("tabular text-xs font-medium", market.deltaPct >= 0 ? "text-bull" : "text-bear")}>
                {formatSignedPercent(market.deltaPct)}
              </span>
              <span className="tabular text-[10px] text-muted-foreground">{market.posts}</span>
            </span>
          </button>
        ))}
      </div>
    </SidebarCard>
  );
}

export function TrendingDiscussions({
  topics,
  onSelectTopic,
}: {
  topics: TrendingTopic[];
  onSelectTopic: (topic: string) => void;
}) {
  return (
    <SidebarCard title="Trending Discussions" icon={<FlameIcon className="size-4 text-gold" />}>
      <div className="divide-y divide-border/70">
        {topics.map((topic) => (
          <button
            key={topic.title}
            type="button"
            onClick={() => onSelectTopic(topic.title)}
            className="flex w-full items-center gap-2 px-2 py-2 text-left transition-colors hover:bg-accent/40"
          >
            <span className="text-xs font-medium">{topic.title}</span>
            <span className="ml-auto text-[10px] text-muted-foreground">
              {topic.posts} posts
            </span>
          </button>
        ))}
      </div>
    </SidebarCard>
  );
}

export function SuggestedTraders({
  traders,
  following,
  onFollowToggle,
  onOpenProfile,
}: {
  traders: Array<{ id: string; name: string; handle: string; avatar: string | null; bio: string }>;
  following: string[];
  onFollowToggle: (userId: string) => void;
  onOpenProfile: (userId: string) => void;
}) {
  return (
    <SidebarCard title="Suggested Traders" icon={<CreditCardIcon className="size-4" />}>
      <div className="space-y-1">
        {traders.map((trader) => {
          const isFollowing = following.includes(trader.id);
          return (
            <div
              key={trader.id}
              className="flex items-center gap-2.5 rounded-lg px-2 py-2 transition-colors hover:bg-accent/40"
            >
              <button type="button" onClick={() => onOpenProfile(trader.id)}>
                <UserAvatar user={trader} size="sm" />
              </button>
              <button
                type="button"
                onClick={() => onOpenProfile(trader.id)}
                className="min-w-0 flex-1 text-left"
              >
                <div className="truncate text-xs font-medium">{trader.name}</div>
                <div className="truncate text-[11px] text-muted-foreground">@{trader.handle}</div>
              </button>
              <Button
                size="sm"
                variant={isFollowing ? "outline" : "default"}
                className="shrink-0"
                onClick={() => onFollowToggle(trader.id)}
              >
                {isFollowing ? <UserCheckIcon className="size-3.5" /> : <UserPlusIcon className="size-3.5" />}
                {isFollowing ? "Following" : "Follow"}
              </Button>
            </div>
          );
        })}
      </div>
    </SidebarCard>
  );
}