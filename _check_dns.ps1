#!/usr/bin/env pwsh
# Check if nowicki.trade DNS has propagated to Railway

Write-Host "=== Checking DNS propagation for nowicki.trade ===" -ForegroundColor Cyan

$targetIP = "69.46.46.100"
$domain = "nowicki.trade"

Write-Host "`nDNS Resolution:" -ForegroundColor Yellow
try {
    $dns = Resolve-DnsName $domain -Type A -ErrorAction Stop
    $currentIP = $dns.IPAddress
    Write-Host "  $domain -> $currentIP"
    
    if ($currentIP -eq $targetIP) {
        Write-Host "  ✓ DNS CORRECT!" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Still old IP (Namecheap parking)" -ForegroundColor Red
        Write-Host "  Expected: $targetIP" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ✗ DNS lookup failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`nHTTP Test:" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "https://$domain/" -Method Get -TimeoutSec 15 -UseBasicParsing -ErrorAction Stop
    Write-Host "  Status: $($response.StatusCode)" -ForegroundColor Green
    Write-Host "  Server: $($response.Headers.Server)"
    
    if ($response.Content -match '<title>([^<]+)</title>') {
        Write-Host "  Title: $($matches[1])"
    }
    
    if ($response.Headers.Server -eq 'railway-hikari') {
        Write-Host "`n  ✓✓✓ SITE IS LIVE ON RAILWAY! ✓✓✓" -ForegroundColor Green
    } elseif ($response.Headers.Server -eq 'namecheap-web') {
        Write-Host "`n  ✗ Still showing Namecheap parking page" -ForegroundColor Red
        Write-Host "  DNS may not have propagated yet (TTL ~5-30 min)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ✗ HTTP request failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n=== Done ===" -ForegroundColor Cyan
