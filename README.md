# mysquidscanner

Fast asyncio port scanner that pivots through a misconfigured **Squid proxy** using the `CONNECT` method. It reaches internal services (localhost, internal subnets) that the firewall blocks from the outside, and grabs a banner from every open port.

Built for CTFs, Hack The Box labs and authorized penetration tests.

Full write-up on Squid port 3128, open proxy abuse, pivoting and hardening:
**[Squid Proxy Port 3128: what it is, how it works, security risks](https://en.hackita.it/articoli/porta-3128-squid-proxy/)**
(also in [Italian](https://hackita.it/articoli/porta-3128-squid-proxy/)).

## Features

- Asyncio engine, 150 concurrent workers by default
- Classifies every port through the proxy: `OPEN`, `BLOCKED` (403 Squid policy), `CLOSED`, `AUTH` (407), `TIMEOUT`, `ERROR`
- Universal banner grabbing: passive read first (SSH, FTP, SMTP, MySQL...), active `GET /` fallback
- Proxy Basic authentication support (`user:pass@host:port`)
- Configurable timeout and retries, hard timeouts so workers never hang
- Saves open ports to `Squid_Port.txt`
- No external dependencies, Python 3.8+ standard library only

## Usage

```bash
python3 mysquid.py --proxy 10.10.10.1:3128 --target 127.0.0.1 --ports 22,80,443
python3 mysquid.py --proxy 10.10.10.1:3128 --target 192.168.1.50 --allports
python3 mysquid.py --proxy user:pass@10.10.10.1:3128 --target 127.0.0.1 --show-blocked
```

| Option | Description | Default |
|---|---|---|
| `--proxy` | Squid proxy: `[user:pass@]host:port` | required |
| `--target` | IP/hostname to scan through the proxy | required |
| `--ports` | Comma-separated ports | built-in list of common ports |
| `--allports` | Scan all 65535 ports | off |
| `--workers` | Concurrent connections | 150 |
| `--timeout` | Timeout per attempt (seconds) | 2.0 |
| `--retries` | Retries on timeout/error | 2 |
| `--show-blocked` | Print ports denied by Squid policy (403) | off |

## Output

```text
[+] PORT 22 OPEN -> SSH-2.0-OpenSSH_8.9p1 Ubuntu-3ubuntu0.6
[+] PORT 3306 OPEN -> 5.7.42-0ubuntu0.18.04.1
[*] OPEN PORTS: 22, 3306
[*] Results saved to: /current/dir/Squid_Port.txt
```

A `BLOCKED` port is denied by the Squid ACL, not necessarily closed on the target.

## Disclaimer

For educational use and authorized environments only (labs, CTFs, systems you own or have written permission to test). The author is not responsible for misuse.

## More from Hackita

Offensive security and ethical hacking: [hackita.it](https://hackita.it/articoli/porta-3128-squid-proxy/)
