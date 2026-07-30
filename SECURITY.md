# Security policy

## Reporting a vulnerability

Please report security issues **privately**, not as a public issue.

- Preferred: open a private advisory through GitHub —
  [Report a vulnerability](https://github.com/ZevnixAi-Applications/OpenMob/security/advisories/new)
- Or email **pandatritik47@gmail.com** with `OpenMob security` in the subject.

Include what you were running (OpenMob version, host OS, device platform), the
steps to reproduce, and what an attacker gains. A proof of concept helps.

You can expect an acknowledgement within **5 working days** and an assessment
within **10**. OpenMob is maintained by a small team, so please allow reasonable
time for a fix before disclosing publicly. Reporters are credited in the release
notes unless they ask not to be.

## Supported versions

OpenMob is pre-1.0 and moves quickly. Only the **latest release** receives
security fixes; there are no backports to earlier tags.

## Security model — read this before exposing the engine

The engine controls real devices, so treat it as a privileged local service.

- **It binds `127.0.0.1:8930` by default.** Only processes on your machine can
  reach it. This is the intended configuration.
- **There is no authentication.** Any client that can reach the engine's HTTP or
  WebSocket API has the engine's full authority: tap and type on your devices,
  install and uninstall apps, read app logs and crash reports, push and pull
  files, and attach a debugger.
- **`openmob serve --host 0.0.0.0` removes the only boundary there is.** It is
  provided for LAN use on networks you control. On an untrusted network —
  a café, a coworking space, a conference — anyone on that network gets
  unauthenticated control of every device attached to your machine. The engine
  also advertises itself over mDNS, so it does not need to be discovered by luck.
  If you need remote access, put it behind an SSH tunnel or a VPN rather than
  binding a public interface.
- **Devices must already be unlocked and trusted.** OpenMob uses the platforms'
  own developer channels — `adb` on Android, a signed WebDriverAgent runner on
  iOS. It cannot bypass a lock screen, USB-debugging consent, or Apple's code
  signing, and it does not try to.
- **Nothing is sent off your machine.** Screens, logs, crash reports, and files
  stay local. See [PRIVACY.md](PRIVACY.md).

Reports that amount to "the API is unauthenticated when I deliberately bind it
to a public interface" describe documented behaviour rather than a vulnerability
— though concrete proposals for adding authentication are very welcome as
issues.
