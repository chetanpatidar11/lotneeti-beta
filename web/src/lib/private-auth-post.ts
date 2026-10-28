import { request } from "node:http";

// Native fetch can replace Host with the loopback destination on deployed Node.
// This private transport must retain the public host for Django's host checks.
export function privateAuthPost(url: string, headers: Record<string, string>, body: string): Promise<Response> {
  const target = new URL(url);
  if (target.protocol !== "http:" || target.hostname !== "127.0.0.1") {
    return Promise.reject(new Error("Authentication requires the private API transport."));
  }
  return new Promise((resolve, reject) => {
    const outgoing = request(target, { method: "POST", headers }, (incoming) => {
      const chunks: Buffer[] = [];
      let bytes = 0;
      incoming.on("error", reject);
      incoming.on("data", (chunk: Buffer) => {
        bytes += chunk.length;
        if (bytes > 1024 * 1024) {
          outgoing.destroy(new Error("Authentication response is too large."));
        } else chunks.push(chunk);
      });
      incoming.on("end", () => {
        const status = incoming.statusCode ?? 502;
        if (status >= 300 && status < 400) {
          reject(new Error("Unexpected authentication redirect."));
          return;
        }
        const responseHeaders = new Headers();
        for (let index = 0; index < incoming.rawHeaders.length; index += 2) {
          responseHeaders.append(incoming.rawHeaders[index], incoming.rawHeaders[index + 1]);
        }
        resolve(new Response(status === 204 || status === 205 ? null : Buffer.concat(chunks), {
          status, headers: responseHeaders,
        }));
      });
    });
    outgoing.setTimeout(30_000, () => outgoing.destroy(new Error("Authentication request timed out.")));
    outgoing.on("error", reject);
    outgoing.end(body);
  });
}
