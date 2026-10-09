# Android beta package

This Capacitor 8 project packages a small local launch screen. Its **Open LotNeeti** button opens the hosted HTTPS Next.js site through the official Capacitor Browser plugin. The hosted site remains the application UI and keeps its existing server-rendered routes and same-site session cookies. The package contains no API secret or account data.

This is a **limited beta launcher**, not yet a bundled offline/mobile client. It requires a working HTTPS site and a browser on the device. `server.url` is intentionally absent because [Capacitor documents it as a live-reload option, not a production setting](https://capacitorjs.com/docs/config). The web code currently uses Next.js server rendering, so it cannot be copied into Capacitor's static `webDir` without a separate client-side implementation. Do not describe this launcher as a complete native wrapper in release notes.

## Build

Prerequisites: Node 22+, Android Studio 2025.2.1+ with an Android SDK (API 36 for the generated project), and a deployed HTTPS LotNeeti site. The generated project has min SDK 24 and target SDK 36. See the [Capacitor Android setup](https://capacitorjs.com/docs/getting-started/environment-setup) for the toolchain.

From this directory:

```sh
npm ci
VITE_LOTNEETI_WEB_URL=https://your-beta-host.example npm run android:sync
npm run test
npm run typecheck
npm run android:open
```

In Android Studio, select an emulator/device and run the app. For a local debug APK, use **Build > Build Bundle(s) / APK(s) > Build APK(s)** or `cd android && ./gradlew assembleDebug`; the APK is under `android/app/build/outputs/apk/debug/`. A release APK requires a private signing key held outside this repository. Keep the keystore and its passwords outside Git. The `com.lotneeti.beta` application ID is temporary and must be reviewed before any store release.

`VITE_LOTNEETI_WEB_URL` is public configuration baked into the app, not a secret. The build rejects HTTP, credentials, paths, queries and fragments. Run `android:sync` again whenever the destination or launch screen changes; generated web assets under `android/app/src/main/assets/public` are ignored by Git. Do not ship an APK built against the synthetic test URL.

## Release check

On a physical Android device, verify that the button opens the correct HTTPS beta host, sign-in completes, returning to LotNeeti and reopening keeps the expected session, each primary destination works, CSV download works, and the app handles offline/reconnect cleanly. The native APK/device checks are outstanding in this workspace because Android Studio, SDK and Java are not installed here. The separate P0 requirement for a full Capacitor wrapper over the web application also remains open until the Next.js UI can be packaged as static client assets or an approved mobile-specific architecture replaces this launcher.
