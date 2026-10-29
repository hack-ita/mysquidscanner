#!/usr/bin/env python3
"""
HACKITA SQUID SCANNER - ASYNCIO RELIABILITY EDITION
High-performance, reliable Squid CONNECT port scanner with Universal Banner Grabbing.
"""
import argparse
import asyncio
import base64
import sys
import os
import re

# --- HACKITA BRANDING COLORS ---
RED    = "\033[38;5;196m"  # Hackita Bright Red
DRED   = "\033[38;5;88m"   # Hackita Dark Red
WHITE  = "\033[38;5;255m"  # Pure White / Silver
BLACK  = "\033[38;5;236m"  # Dark Grey (visible on black background)
RESET  = "\033[0m"
BOLD   = "\033[1m"

# --- HACKITA TEXT LOGO ---
HACKITA_LOGO = f"""
{WHITE}{BOLD}██╗  ██╗ █████╗  ██████╗██╗  ██╗{RED}██╗████████╗ █████╗ {RESET}
{WHITE}{BOLD}██║  ██║██╔══██╗██╔════╝██║ ██╔╝{RED}██║╚══██╔══╝██╔══██╗{RESET}
{WHITE}{BOLD}███████║███████║██║     █████╔╝ {RED}██║   ██║   ███████║{RESET}
{WHITE}{BOLD}██╔══██║██╔══██║██║     ██╔═██╗ {RED}██║   ██║   ██╔══██║{RESET}
{WHITE}{BOLD}██║  ██║██║  ██║╚██████╗██║  ██╗{RED}██║   ██║   ██║  ██║{RESET}
{WHITE}{BOLD}╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝{RED}╚═╝   ╚═╝   ╚═╝  ╚═╝{RESET}
{DRED}       S Q U I D   S C A N N E R   -   S S R F   E D I T I O N {RESET}
"""

DEFAULT_PORTS = [21,22,23,25,53,69,80,109,110,123,135,137,138,139,143,156,389,443,
                 445,546,547,993,995,1433,3306,3389,5432,5985,6379,8080,8443,10000,
                 3128,8000,8888,9000,9200,27017]

def parse_proxy(proxy: str):
    auth = None
    if "://" in proxy:
        proxy = proxy.split("://", 1)[1]
    if "@" in proxy:
        auth, proxy = proxy.rsplit("@", 1)
    host, port = proxy.rsplit(":", 1)
    return host, int(port), auth

def clean_banner(data: bytes) -> str:
    if not data:
        return ""
    try:
        text = data.decode('utf-8', errors='ignore')
        text = re.sub(r'[^\x20-\x7E]+', ' ', text).strip()
        if text.startswith("HTTP/"):
            return text.split('\r\n')[0]
        return text[:60]
    except Exception:
        return ""

async def grab_banner(reader, writer, target_host):
    """Prova a rubare il banner in modo UNIVERSALE, con timeout rigidi anti-blocco."""
    banner_text = ""
    
    # 1. Prova Lettura Passiva (SSH, FTP, SMTP, MySQL, ecc.)
    try:
        banner_data = await asyncio.wait_for(reader.read(1024), timeout=0.4)
        banner_text = clean_banner(banner_data)
    except (asyncio.TimeoutError, ConnectionResetError, BrokenPipeError):
        pass
        
    # 2. Se non ha parlato, prova in modo attivo con GET HTTP (Universale)
    if not banner_text:
        try:
            req = f"GET / HTTP/1.0\r\nHost: {target_host}\r\n\r\n"
            writer.write(req.encode())
            await writer.drain()
            
            banner_data = await asyncio.wait_for(reader.read(1024), timeout=0.4)
            banner_text = clean_banner(banner_data)
        except (asyncio.TimeoutError, ConnectionResetError, BrokenPipeError):
            pass
            
    return banner_text if banner_text else "Unknown Service"

async def check_port(proxy_host, proxy_port, auth_b64, target_host, target_port, timeout, retries):
    for attempt in range(retries + 1):
        writer = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(proxy_host, proxy_port), timeout=timeout
            )
            
            req = (
                f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
                f"Host: {target_host}:{target_port}\r\n"
                f"Proxy-Connection: keep-alive\r\n"
            )
            if auth_b64:
                req += f"Proxy-Authorization: Basic {auth_b64}\r\n"
            req += "\r\n"
            
            writer.write(req.encode())
            await writer.drain()

            resp = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), timeout=timeout)
            status_line = resp.split(b'\r\n')[0].decode(errors="ignore")
            
            if " 200 " in status_line:
                # La porta è aperta! Proviamo a prendere il banner (non bloccherà mai)
                service = await grab_banner(reader, writer, target_host)
                return "OPEN", target_port, service
            elif " 403 " in status_line:
                return "BLOCKED", target_port, ""
            elif " 407 " in status_line:
                return "AUTH", target_port, ""
            else:
                return "CLOSED", target_port, ""

        except (asyncio.TimeoutError, ConnectionResetError, OSError):
            if attempt == retries:
                return "TIMEOUT", target_port, ""
            await asyncio.sleep(0.3)
            continue
        except Exception:
            if attempt == retries:
                return "ERROR", target_port, ""
            await asyncio.sleep(0.3)
            continue
        finally:
            if writer:
                writer.close()
                try:
                    # TIMEOUT FORZATO SULLA CHIUSURA: impedisce al worker di bloccarsi
                    await asyncio.wait_for(writer.wait_closed(), timeout=0.1)
                except Exception:
                    pass

async def worker(queue, proxy_host, proxy_port, auth_b64, target_host, timeout, retries, stats, open_ports, print_lock, progress_data, total_ports, show_blocked):
    while True:
        try:
            port = queue.get_nowait()
        except asyncio.QueueEmpty:
            break

        status, p, service = await check_port(proxy_host, proxy_port, auth_b64, target_host, port, timeout, retries)
        
        async with print_lock:
            stats[status] += 1
            progress_data[0] += 1
            
            if status == "OPEN":
                open_ports.append(p)
                sys.stdout.write("\r\033[K")
                service_str = f" {WHITE}-> {service}{RESET}" if service else ""
                print(f"{RED}{BOLD}[+] PORT {p} OPEN{RESET}{service_str}")
            elif status == "BLOCKED" and show_blocked:
                sys.stdout.write("\r\033[K")
                print(f"{DRED}[!] PORT {p} BLOCKED (Squid Policy 403){RESET}")
            elif status == "AUTH":
                if stats["AUTH"] == 1:
                    sys.stdout.write("\r\033[K")
                    print(f"{RED}{BOLD}[!] PROXY REQUIRES AUTH (407) - Use --proxy user:pass@host:port{RESET}")
            
            if progress_data[0] % 50 == 0 or progress_data[0] == total_ports:
                sys.stdout.write(f"\r\033[K{BLACK}[*] Scanned {progress_data[0]}/{total_ports} ports...{RESET}")
                sys.stdout.flush()
                
        queue.task_done()
        await asyncio.sleep(0.01)

async def scan_all_ports(proxy_host, proxy_port, auth_b64, target_host, ports, workers, timeout, retries, show_blocked):
    print(HACKITA_LOGO)
    
    print(f"{DRED}=================================================={RESET}")
    print(f"{RED}{BOLD}[*] TARGET: {target_host}{RESET}")
    print(f"{DRED}[*] Proxy: {proxy_host}:{proxy_port} | Workers: {workers} | Timeout: {timeout}s | Retries: {retries}{RESET}")
    print(f"{DRED}=================================================={RESET}\n")

    queue = asyncio.Queue()
    for port in ports:
        queue.put_nowait(port)

    stats = {"OPEN": 0, "BLOCKED": 0, "CLOSED": 0, "TIMEOUT": 0, "ERROR": 0, "AUTH": 0}
    open_ports = []
    print_lock = asyncio.Lock()
    progress_data = [0]
    total_ports = len(ports)

    tasks = []
    for _ in range(workers):
        tasks.append(asyncio.create_task(
            worker(queue, proxy_host, proxy_port, auth_b64, target_host, timeout, retries, stats, open_ports, print_lock, progress_data, total_ports, show_blocked)
        ))
    
    await asyncio.gather(*tasks)
    
    sys.stdout.write("\r\033[K")
    sys.stdout.flush()

    # --- SUMMARY ---
    print(f"\n{DRED}=================================================={RESET}")
    print(f"{RED}{BOLD}[*] FINAL RESULTS FOR {target_host}{RESET}")
    print(f"{RED}  [OPEN]    {stats['OPEN']} {WHITE}(Ports successfully reached){RESET}")
    print(f"{DRED}  [BLOCKED] {stats['BLOCKED']} {WHITE}(Denied by Squid policy, NOT closed){RESET}")
    print(f"{BLACK}  [CLOSED]  {stats['CLOSED']} (Refused by target){RESET}")
    print(f"{BLACK}  [TIMEOUT] {stats['TIMEOUT']} (Failed after {retries} retries){RESET}")
    if stats['ERROR'] > 0:
        print(f"{RED}  [ERROR]   {stats['ERROR']} {WHITE}(Connection failed){RESET}")
    
    sorted_ports = sorted(open_ports)
    
    if sorted_ports:
        print(f"\n{RED}{BOLD}[*] OPEN PORTS: {', '.join(map(str, sorted_ports))}{RESET}")
        
        # --- SALVATAGGIO SU FILE (Squid_Port.txt) ---
        filename = "Squid_Port.txt"
        with open(filename, "w") as f:
            f.write("[*] OPEN PORTS:\n")
            for p in sorted_ports:
                f.write(f"{p}\n")
        
        filepath = os.path.abspath(filename)
        print(f"{DRED}[*] Results saved to: {WHITE}{filepath}{RESET}")
    else:
        print(f"\n{DRED}[!] No OPEN ports found.{RESET}")
        
    print(f"{DRED}=================================================={RESET}")
    
    # --- HACKITA FOOTER ---
    print(f"\n{DRED}=================================================={RESET}")
    print(f"{RED}{BOLD}       DISCOVER MORE AT HACKITA{RESET}")
    print(f"{DRED}=================================================={RESET}")
    print(f" {WHITE}🇮🇹 Italian  : {RED}https://hackita.it/articoli/porta-3128-squid-proxy/{RESET}")
    print(f" {WHITE}🇬🇧 English  : {RED}https://en.hackita.it/articoli/porta-3128-squid-proxy/{RESET}")
    print(f" {WHITE}🇪🇸 Spanish  : {RED}https://es.hackita.it/articoli/porta-3128-squid-proxy/{RESET}")
    print(f" {WHITE}🇩🇪 German   : {RED}https://de.hackita.it/articoli/porta-3128-squid-proxy/{RESET}")
    print(f" {WHITE}🇵🇹 Portuguese: {RED}https://pt.hackita.it/articoli/porta-3128-squid-proxy/{RESET}")
    print(f" {WHITE}🇫🇷 French   : {RED}https://fr.hackita.it/articoli/porta-3128-squid-proxy/{RESET}")
    print(f"{DRED}=================================================={RESET}\n")

def main():
    epilog_text = f"""
{WHITE}{BOLD}WHAT IS THIS TOOL?{RESET}
This script tests for {RED}{BOLD}SSRF (Server-Side Request Forgery){RESET} and 
performs internal network pivoting through a misconfigured Squid proxy.

{WHITE}{BOLD}OUTPUT FILE:{RESET}
At the end of the scan, a file named {RED}Squid_Port.txt{RESET} is created 
in the current directory, containing a clean list of all open ports.

{WHITE}{BOLD}HOW TO USE IT:{RESET}
python3 squid.py --proxy 10.10.10.1:3128 --target 127.0.0.1 --ports 22,80,443
python3 squid.py --proxy 10.10.10.1:3128 --target 192.168.1.50 --allports
"""

    ap = argparse.ArgumentParser(
        description="Hackita Squid Scanner - Asyncio Universal Edition",
        epilog=epilog_text,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--proxy", required=True, help="Squid proxy to use: [user:pass@]host:port")
    ap.add_argument("--target", required=True, help="Target IP/hostname to scan via the proxy")
    ap.add_argument("--ports", help="Specific ports to scan (e.g., 22,80,443)")
    ap.add_argument("--allports", action="store_true", help="Scan ALL 65535 ports")
    ap.add_argument("--workers", type=int, default=150, help="Concurrent connections (default: 150)")
    ap.add_argument("--timeout", type=float, default=2.0, help="Timeout per attempt in seconds (default: 2.0)")
    ap.add_argument("--retries", type=int, default=2, help="Number of retries if timeout/error (default: 2)")
    ap.add_argument("--show-blocked", action="store_true", help="Show ports blocked by Squid policy (403)")
    args = ap.parse_args()

    proxy_host, proxy_port, auth = parse_proxy(args.proxy)
    auth_b64 = base64.b64encode(auth.encode()).decode() if auth else None

    if args.allports:
        ports = range(1, 65536)
    elif args.ports:
        ports = [int(x.strip()) for x in args.ports.split(",") if x.strip()]
    else:
        ports = DEFAULT_PORTS

    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            
        asyncio.run(scan_all_ports(
            proxy_host, proxy_port, auth_b64, args.target, 
            list(ports), args.workers, args.timeout, args.retries, args.show_blocked
        ))
    except KeyboardInterrupt:
        print(f"\n{RED}[!] Scan interrupted by user.{RESET}")
        sys.exit(0)

if __name__ == "__main__":
    main()
