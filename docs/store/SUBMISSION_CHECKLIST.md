# OpenMob — store submission checklist

What is already done in the repo, and the exact human steps that remain.

## Done in this repo

- [x] App icon (1024x1024 master at `app/assets/icon/icon.png`, Android
      adaptive foreground + `#16181D` background, iOS full-bleed variant)
      applied to Android, iOS, and macOS via `flutter_launcher_icons`.
- [x] Android release signing: upload keystore at
      `~/Desktop/KeysIdentifiers/openmob/upload-keystore.jks` (passwords in
      `README.txt` next to it — BACK IT UP), wired via gitignored
      `app/android/key.properties`; `flutter build appbundle --release`
      produces a verified signed AAB.
- [x] iOS: bundle id `ai.zevnix.openmob`, team `76Z3N79K53` set in the Xcode
      project (see `docs/store/IOS_SUBMISSION.md` for remaining iOS steps).
- [x] Privacy policy: `PRIVACY.md` (repo root).
- [x] Listing copy: `docs/store/PLAY_LISTING.md`,
      `docs/store/APPSTORE_LISTING.md`.

## Remaining human steps — Google Play

1. **Play Console account**: create/verify a Google Play developer account
   for Zevnix AI ($25 one-time). Complete identity verification.
2. Create the app in Play Console: name **OpenMob**, package
   `ai.zevnix.openmob`, free.
3. Publish `PRIVACY.md` at a public URL (GitHub is fine) and set it as the
   privacy policy URL.
4. Fill store listing from `PLAY_LISTING.md` (short/full description, icon —
   upload a 512x512 export of `app/assets/icon/icon.png` — and a 1024x500
   feature graphic, which still needs to be designed).
5. Complete the IARC content-rating questionnaire and Data safety form with
   the answers in `PLAY_LISTING.md`.
6. Upload screenshots (see plan below).
7. Upload `app/build/app/outputs/bundle/release/app-release.aab` to an
   internal-testing track first; opt in to Play App Signing (Google keeps the
   app signing key; our keystore becomes the upload key).
8. Add the reviewer note (demo mode) from `PLAY_LISTING.md`, then promote to
   production review.

## Remaining human steps — App Store

1. **App Store Connect app record**: with the Zevnix AI team account
   (76Z3N79K53), register bundle id `ai.zevnix.openmob` at
   developer.apple.com → Identifiers, then create the app in App Store
   Connect (name OpenMob, SKU e.g. `openmob-ios`).
   Note: the team's Individual→Organization conversion is in progress; App
   Store submission may need to wait for it to settle.
2. Re-run `flutter build ipa --release` (see `IOS_SUBMISSION.md` for the
   current blocker) and upload via Transporter or
   `xcrun altool`/`xcodebuild -exportArchive`.
3. Fill the listing from `APPSTORE_LISTING.md` (subtitle, description,
   keywords, privacy "Data Not Collected", age rating 4+).
4. Paste the local-network justification and the demo-mode note from
   `APPSTORE_LISTING.md` into App Review notes.
5. Upload screenshots (see plan below) and submit for review.

## Screenshot plan

Store screenshots must be captured by a human (or on-device automation) —
they cannot be produced headlessly from this repo today because the phone UI
is what needs to be shown.

- **Note (this branch)**: `app/lib` on this branch has no demo mode yet — it
  is the desktop UI (sidebar + device mirror) that connects to a live engine.
  If/when the mobile branch's demo mode ("Try Demo") lands, capture all store
  screenshots in demo mode so no hardware setup is needed and no personal
  data can leak into frames.
- Capture in the app's dark theme, engine connected (or demo), showing:
  1. Device list / connect screen
  2. Live mirror of a device with the toolbar visible
  3. Demo mode running (once available)
- **Play Store**: phone screenshots (min 2, 16:9 or 9:16, ≥1080px) — use a
  Pixel emulator or device: `flutter run --release`, then
  `adb exec-out screencap -p > shot1.png`. Optionally 7"/10" tablet sets.
- **App Store**: 6.9" (iPhone 16 Pro Max / 15 Pro Max, 1320x2868) and 6.5"
  (1284x2778 or 1242x2688) sets, min 1 each — use iOS Simulator
  (`xcrun simctl io booted screenshot shot1.png`); App Store Connect can
  reuse 6.9" for smaller sizes.
- Feature graphic for Play (1024x500): design separately (can be derived
  from the icon mark + charcoal/green palette; `scripts/gen_icon.py` has the
  colors).
