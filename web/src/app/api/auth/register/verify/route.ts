import { authPost } from "@/lib/auth-post";

export async function POST(request: Request) {
  return authPost(request, "auth/register/verify/", true);
}
