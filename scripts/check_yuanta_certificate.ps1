# MARKET_AI_HUB — generic Windows certificate-store preflight（唯讀）
# IMPORTANT: store non-empty / unexpired != Yuanta certificate identity or official signature verification.

$ErrorActionPreference = "Continue"

try {
  $certs = @(Get-ChildItem Cert:\CurrentUser\My -ErrorAction Stop)
  $now = Get-Date
  $valid = @($certs | Where-Object { $_.NotAfter -gt $now })
  Write-Host "store_access: true"
  Write-Host "certificate_store_nonempty: $(if ($certs.Count -gt 0) { 'true' } else { 'false' })"
  Write-Host "certificate_count: $($certs.Count)"
  Write-Host "certificate_store_has_unexpired: $(if ($valid.Count -gt 0) { 'true' } else { 'false' })"
  if ($certs.Count -gt 0) {
    $minDays = ($certs | ForEach-Object { ($_.NotAfter - $now).Days } | Measure-Object -Minimum).Minimum
    Write-Host "days_until_earliest_expiry: $minDays"
  }
  Write-Host "yuanta_certificate_identity_verified: false"
  Write-Host "yuanta_official_signature_verified: false"
  Write-Host "verification_note: GENERIC_STORE_ONLY_REQUIRES_OFFICIAL_YUANTA_SIGNATURE_CHECK"
  # Intentionally never prints subject, issuer, thumbprint, PFX path, or private-key metadata.
} catch {
  Write-Host "store_access: false"
  Write-Host "certificate_store_nonempty: false"
  Write-Host "certificate_store_has_unexpired: false"
  Write-Host "yuanta_certificate_identity_verified: false"
  Write-Host "yuanta_official_signature_verified: false"
  Write-Host "verification_note: CERTIFICATE_STORE_UNAVAILABLE"
  exit 1
}
