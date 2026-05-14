# Unhooked Mobile

React Native (Expo) app for the Unhooked iOS/Android client. Talks to the same Flask backend as the web app via `/api/v1/`.

## Prerequisites

- Node.js 18+ and `npm`
- The Flask backend running locally (see the [root README](../README.md))
- One of:
  - **Xcode + iOS Simulator** (Mac only) — Path A below
  - **Expo Go app on a physical phone** — Path B below

## Install dependencies

```bash
cd mobile
npm install
```

If you hit an `ERESOLVE` peer-dependency error, use:

```bash
npm install --legacy-peer-deps
```

This is the standard workaround in the Expo ecosystem — peer ranges between React, React Native, and Expo Router can be overly strict but are compatible at runtime.

## Start the dev server

```bash
npm start
```

This opens the Expo dev tools and shows a QR code. From here, pick Path A (simulator) or Path B (phone).

---

## Path A — iOS Simulator (Mac, requires Xcode)

Best for fast iteration on a Mac. Roughly 30–60 minutes for a fresh Xcode install (~15 GB download).

1. **Install Xcode**: Mac App Store → search "Xcode" → Install. (Free, but large.)
2. **Open Xcode once** and accept the license / let it install additional components.
3. **Point the command-line tools at the full Xcode app**:
   ```bash
   sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
   ```
4. **Sanity-check the Simulator opens**:
   ```bash
   open -a Simulator
   ```
5. In the terminal running `npm start`, press **`i`** to launch the app in the iOS Simulator.

If Expo complains "Xcode must be fully installed" even after the above, accept the license explicitly:

```bash
sudo xcodebuild -license accept
```

Then stop `npm start` (Ctrl+C) and run it again.

### Stopping the simulator

- **Ctrl+C** in the `npm start` terminal stops the Expo/Metro bundler.
- The Simulator app keeps running — quit it with **Cmd+Q** if you want it fully closed (otherwise leaving it open speeds up the next launch).

---

## Path B — Physical phone via Expo Go (no Xcode required)

Faster for demos and works on any Mac/Windows/Linux machine.

1. **Install [Expo Go](https://expo.dev/go)** from the App Store (iOS) or Play Store (Android) on your phone.
2. Make sure your phone and your computer are on the **same Wi-Fi network**.
3. **Update the API base URL** so the phone can reach the Flask backend — `localhost` won't resolve from the phone. Find your Mac's local IP:
   ```bash
   ifconfig | grep "inet " | grep -v 127.0.0.1
   # e.g. 192.168.1.42
   ```
   Then edit `mobile/services/api.ts` and replace `localhost` with that IP:
   ```ts
   const BASE_URL = __DEV__
     ? 'http://192.168.1.42:5001/api/v1'   // ← your Mac's IP
     : 'https://your-production-url.com/api/v1';
   ```
4. **Scan the QR code** shown in the `npm start` terminal:
   - iOS: use the built-in Camera app, tap the banner to open in Expo Go.
   - Android: use the "Scan QR code" button inside Expo Go.

The app will hot-reload on save just like the simulator.

### Common gotchas

- **"Network request failed"** on the phone almost always means:
  - The IP in `api.ts` is wrong, OR
  - Flask is bound to `127.0.0.1` instead of `0.0.0.0`, OR
  - Mac firewall is blocking port 5001.
- **Wi-Fi network changed** (e.g. café vs. home) — your Mac's IP probably changed too. Re-edit `api.ts`.

---

## Backend ports vs. environments

| Environment | Flask port | Database |
|---|---|---|
| `FLASK_ENV=development` | 5001 | `database_dev.db` |
| `FLASK_ENV=production` | 5000 | `database_prod.db` |

The mobile app defaults to **port 5001 (dev)** in `services/api.ts`. If the web shows different data than the simulator, you're probably running the prod Flask (port 5000) while mobile is pointed at 5001 — start the dev Flask instead, or update the URL.
