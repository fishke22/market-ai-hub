# MARKET_AI_HUB — check 元大憑證（唯讀，不 export private key、不顯示完整 subject）

$ErrorActionPreference = "Continue"

# 只列「個人憑證 store」的憑證數量與最早到期日，遮罩 subject
try {
  $certs = Get-ChildItem Cert:\CurrentUser\My -ErrorAction Stop
  if (-not $certs) {
    Write-Host "certificate_present: false"
  } else {
    $now = Get-Date
    $minDays = ($certs | ForEach-Object { ($_.NotAfter - $now).Days } | Measure-Object -Minimum).Minimum
    $valid = ($certs | Where-Object { $_.NotAfter -gt $now }).Count
    Write-Host "certificate_present: true"
    Write-Host "certificate_count: $($certs.Count)"
    Write-Host "certificate_valid: $(if ($valid -gt 0) { 'true' } else { 'false' })"
    Write-Host "days_until_expiry: $minDays"
    # 不顯示 subject / thumbprint（避免 PII）
  }
} catch {
  Write-Host "certificate_present: false"
  Write-Host "store_access: false"
}
