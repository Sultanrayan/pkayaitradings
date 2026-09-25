"use client";

import { Users, Zap } from "lucide-react";

import { PageHeader, EmptyState } from "@/components/shared/primitives";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/** Community page: a starting point for traders, ideas and shared analysis. */
export function CommunityView() {
  return (
    <div className="space-y-6">
      <PageHeader
        title={
          <span className="flex items-center gap-2">
            <Users className="size-5" /> Community
          </span>
        }
        description="Share ideas, discuss signals and learn with other traders."
      />

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="size-4" /> Signal bytes
            </CardTitle>
            <CardDescription>Short trade ideas from the community.</CardDescription>
          </CardHeader>
          <CardContent>
            <EmptyState>Contributions appear here once the community opens.</EmptyState>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Guidelines</CardTitle>
            <CardDescription>Keep the community constructive.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>• Share analysis, not financial advice.</p>
            <p>• Credit the data source where possible.</p>
            <p>• Be respectful and specific.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}