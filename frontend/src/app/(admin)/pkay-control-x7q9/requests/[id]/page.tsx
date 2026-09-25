"use client";

import { useParams } from "next/navigation";

import { AdminRequestDetail } from "@/components/admin/admin-request-detail";

export default function AdminRequestPage() {
  const params = useParams<{ id: string }>();
  return <AdminRequestDetail id={String(params.id)} />;
}
