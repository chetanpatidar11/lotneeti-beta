import { NextRequest, NextResponse } from "next/server";
import { isUuid, proxyWorkspaceRequest } from "@/lib/proxy";

type Context = { params: Promise<{ workspaceId: string; bankId: string; paymentId: string }> };

async function forward(request: NextRequest, context: Context, method: "PATCH" | "DELETE") {
  const { workspaceId, bankId, paymentId } = await context.params;
  if (!isUuid(workspaceId) || !isUuid(bankId) || !isUuid(paymentId)) {
    return NextResponse.json({ message: "Invalid payment." }, { status: 400 });
  }
  return proxyWorkspaceRequest(
    request,
    `workspaces/${workspaceId}/banks/${bankId}/recurring-debits/${paymentId}/`,
    method,
  );
}

export async function PATCH(request: NextRequest, context: Context) {
  return forward(request, context, "PATCH");
}

export async function DELETE(request: NextRequest, context: Context) {
  return forward(request, context, "DELETE");
}
