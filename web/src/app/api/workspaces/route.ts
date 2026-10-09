import { NextRequest } from "next/server";
import { proxyWorkspaceRequest } from "@/lib/proxy";

export async function GET(request: NextRequest) {
  return proxyWorkspaceRequest(request, "workspaces/", "GET");
}

export async function POST(request: NextRequest) {
  return proxyWorkspaceRequest(request, "workspaces/", "POST");
}
