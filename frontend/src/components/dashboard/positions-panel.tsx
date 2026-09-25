"use client";

import { Wallet } from "lucide-react";
import { cn } from "cn";

import { Panel, EmptyState } from "@/components/dashboard/ui-bits";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatNumber, formatPrice } from "@/lib/format";
import type { Position } from "@/lib/types";

export function PositionsPanel({
  positions,
  equity,
}: {
  positions: Position[];
  equity: number | null;
}) {
  return (
    <Panel
      title="Paper Account"
      description="Open positions & equity"
      action={
        <div className="flex items-center gap-2 text-sm">
          <Wallet className="size-4 text-muted-foreground" />
          <span className="tabular font-medium">
            {equity === null ? "—" : `$${formatNumber(equity, 2)}`}
          </span>
        </div>
      }
    >
      {positions.length === 0 ? (
        <EmptyState>No open positions. The system is flat.</EmptyState>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Symbol</TableHead>
              <TableHead>Side</TableHead>
              <TableHead className="text-right">Qty</TableHead>
              <TableHead className="text-right">Entry</TableHead>
              <TableHead className="text-right">Stop</TableHead>
              <TableHead className="text-right">Target</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {positions.map((position) => (
              <TableRow key={`${position.symbol}-${position.side}`}>
                <TableCell className="font-medium">{position.symbol}</TableCell>
                <TableCell>
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-xs font-medium",
                      position.side === "BUY"
                        ? "bg-bull/10 text-bull"
                        : "bg-bear/10 text-bear",
                    )}
                  >
                    {position.side}
                  </span>
                </TableCell>
                <TableCell className="tabular text-right">{formatNumber(position.quantity, 4)}</TableCell>
                <TableCell className="tabular text-right">{formatPrice(position.entry_price)}</TableCell>
                <TableCell className="tabular text-right text-bear">
                  {formatPrice(position.stop_loss)}
                </TableCell>
                <TableCell className="tabular text-right text-bull">
                  {formatPrice(position.take_profit)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Panel>
  );
}
