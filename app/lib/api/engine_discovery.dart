import 'package:multicast_dns/multicast_dns.dart';

/// An engine advertised over mDNS as `_openmob._tcp`.
class DiscoveredEngine {
  const DiscoveredEngine({
    required this.name,
    required this.host,
    required this.port,
  });

  /// Instance name, e.g. "OpenMob Engine on my-mac".
  final String name;

  /// IPv4 address, or the advertised `.local` hostname if no A record came back.
  final String host;

  final int port;

  String get hostPort => '$host:$port';
  String get url => 'http://$host:$port';
}

/// Browses the local network for OpenMob engines (`_openmob._tcp`).
class EngineDiscovery {
  static const String serviceType = '_openmob._tcp.local';

  /// Returns the engines found within [timeout].
  ///
  /// Never throws: mDNS being unavailable (no network, sandbox denial) is
  /// reported as an empty list so callers can fall back to manual entry.
  static Future<List<DiscoveredEngine>> discover({
    Duration timeout = const Duration(seconds: 4),
  }) async {
    final client = MDnsClient();
    final found = <String, DiscoveredEngine>{};
    try {
      await client.start();
      await for (final ptr in client.lookup<PtrResourceRecord>(
        ResourceRecordQuery.serverPointer(serviceType),
        timeout: timeout,
      )) {
        final instance = ptr.domainName;
        await for (final srv in client.lookup<SrvResourceRecord>(
          ResourceRecordQuery.service(instance),
          timeout: const Duration(seconds: 2),
        )) {
          var host = srv.target;
          await for (final a in client.lookup<IPAddressResourceRecord>(
            ResourceRecordQuery.addressIPv4(srv.target),
            timeout: const Duration(seconds: 2),
          )) {
            host = a.address.address;
            break;
          }
          found[instance] = DiscoveredEngine(
            name: instanceLabel(instance),
            host: host,
            port: srv.port,
          );
          break;
        }
      }
    } catch (_) {
      // Treat any mDNS failure as "nothing found".
    } finally {
      client.stop();
    }
    return found.values.toList();
  }

  /// Strips the service-type suffix from a full mDNS domain name.
  static String instanceLabel(String domainName) {
    const suffix = '.$serviceType';
    if (domainName.endsWith(suffix)) {
      return domainName.substring(0, domainName.length - suffix.length);
    }
    return domainName;
  }
}
