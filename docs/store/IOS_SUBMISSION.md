# iOS submission — status and remaining steps

## Status (2026-07-21)

`flutter build ipa --release` **succeeds end to end** on this machine:

- Xcode archive: `app/build/ios/archive/Runner.xcarchive`
- App Store IPA: `app/build/ios/ipa/openmob.ipa` (19.2 MB)
- Bundle id: `ai.zevnix.openmob`, display name OpenMob, version 1.0.0 (1)
- Signing: automatic, team **76Z3N79K53**, "Cloud Managed Apple
  Distribution" certificate (expires 2027-01-03)

The Xcode project pins `DEVELOPMENT_TEAM = 76Z3N79K53` in Debug, Release,
and Profile configurations.

## Remaining steps (need the Apple account, cannot be done from the repo)

1. **Create the App Store Connect app record**
   - developer.apple.com → Certificates, Identifiers & Profiles →
     Identifiers → register `ai.zevnix.openmob` (if the cloud-managed flow
     did not already register it).
   - App Store Connect → My Apps → "+" → New App: platform iOS, name
     **OpenMob**, bundle id `ai.zevnix.openmob`, SKU `openmob-ios`.
   - Caveat: the team's Individual→Organization conversion (to "Zevnix AI")
     is in progress; the seller name will show the individual account name
     until that completes. Decide whether to wait.

2. **Upload the build**
   - Transporter app: drag `app/build/ios/ipa/openmob.ipa`, or
   - `xcrun altool --upload-app --type ios -f app/build/ios/ipa/openmob.ipa
     --apiKey <key-id> --apiIssuer <issuer-id>` (App Store Connect API key).
   - Rebuild first if the source has moved on: `cd app && flutter build ipa
     --release`.

3. **Info.plist** — already done in the repo: `NSLocalNetworkUsageDescription`
   and `NSAppTransportSecurity/NSAllowsLocalNetworking` are set in
   `app/ios/Runner/Info.plist` (iOS 14+ blocks LAN access without them).
   Rebuild picks them up automatically.

4. **Cosmetic**: launch screen still uses the Flutter template placeholder
   (`flutter build ipa` warns about it). Replace
   `ios/Runner/Assets.xcassets/LaunchImage.imageset` with a charcoal
   (#16181D) launch screen before submitting.

5. Complete the listing, privacy label, review notes, and screenshots per
   `APPSTORE_LISTING.md` and `SUBMISSION_CHECKLIST.md`, then submit for
   review.
