import assert from "node:assert/strict";
import { createServer } from "node:http";
import { once } from "node:events";
import { test } from "node:test";
import { authTransport } from "../src/lib/auth-transport";
import { privateAuthPost } from "../src/lib/private-auth-post";

test("real private auth connection preserves public Host, visitor IP, JSON and separate cookies", async () => {
  const received: unknown[] = [];
  const server = createServer(async (request, response) => {
    let body = "";
    for await (const chunk of request) body += chunk;
    received.push({ host: request.headers.host, ip: request.headers["x-real-ip"],
      scheme: request.headers["x-forwarded-proto"], origin: request.headers.origin, body });
    response.writeHead(200, { "content-type": "application/json", "set-cookie": [
      "sessionid=synthetic-session; HttpOnly; Secure", "csrftoken=synthetic-csrf; HttpOnly; Secure",
    ] });
    response.end('{"ok":true}');
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  try {
    const port = (server.address() as { port: number }).port;
    const transport = authTransport("auth/password/login/", "198.51.100.1", true, "https://beta.example.test");
    const response = await privateAuthPost(`http://127.0.0.1:${port}/api/v1/auth/password/login/`, transport.headers, '{}');
    assert.deepEqual(received, [{ host: "beta.example.test", ip: "198.51.100.1", scheme: "https",
      origin: "https://beta.example.test", body: "{}" }]);
    assert.deepEqual(await response.json(), { ok: true });
    assert.equal(response.headers.getSetCookie().length, 2);
  } finally {
    await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  }
});

test("private auth refuses non-loopback destinations", async () => {
  for (const url of ["https://127.0.0.1/", "http://other.example/", "http://127.0.0.1.evil.test/"]) {
    await assert.rejects(privateAuthPost(url, {}, "{}"));
  }
});
