param([string]$Output = 'D:/CodexWork/Outputs/teacher-hobong-local-1.0.15-source')
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$out = [IO.Path]::GetFullPath($Output)
$licensesInRepo = Test-Path -LiteralPath (Join-Path $root 'licenses') -PathType Container
$licenseDir = if ($licensesInRepo) { 'licenses' } else { 'school-dist/portable-0.1.15-4b/licenses' }
if (Test-Path -LiteralPath $out) { throw "Source snapshot already exists: $out" }
New-Item -ItemType Directory -Path $out | Out-Null

# Deliberate allowlist: no real certificates, local configuration, executable,
# GitLab history, developer cache, private evaluation set, or signing material.
$fixed = @(
    '.gitignore', 'LICENSE', 'README.md', 'SOURCE_BUILD.md',
    'THIRD-PARTY-NOTICES.md', 'LEGAL_BASIS.md',
    'requirements.txt', 'requirements-base.txt',
    'desktop/package.json', 'desktop/package-lock.json',
    'desktop/scripts/check-frontend.mjs',
    'desktop/src-tauri/Cargo.toml', 'desktop/src-tauri/Cargo.lock',
    'desktop/src-tauri/build.rs', 'desktop/src-tauri/tauri.conf.json',
    'desktop/src-tauri/capabilities/default.json',
    'packaging/Build-Store.ps1', 'packaging/Build-PublicSource.ps1',
    'packaging/collect-notices.py', 'packaging/certocr-sidecar.spec',
    'packaging/store-identity.json',
    'scripts/certocr_sidecar.py', 'scripts/serve_hobong.py',
    'scripts/evaluate_real.py', 'scripts/patch_hobong_html.py'
)
$files = [Collections.Generic.List[string]]::new()
foreach ($relative in $fixed) { $files.Add($relative) }
foreach ($spec in @(
    @{Path='certocr';Filter='*.py'},
    @{Path='data/dicts';Filter='*'},
    @{Path='data/models';Filter='*'},
    @{Path='desktop/web';Filter='*'},
    @{Path='desktop/src-tauri/src';Filter='*.rs'},
    @{Path='desktop/src-tauri/icons';Filter='*'},
    @{Path='web';Filter='*.html'},
    @{Path='tests';Filter='*.py'},
    @{Path=$licenseDir;Filter='*'}
)) {
    foreach ($file in Get-ChildItem -LiteralPath (Join-Path $root $spec.Path) -File -Recurse -Filter $spec.Filter) {
        if ($file.FullName -match '[\\/](__pycache__|android|ios)[\\/]' -or
            $file.Name -in @('test_real_labels.py','test_evaluation.py')) { continue }
        $rel = [IO.Path]::GetRelativePath($root, $file.FullName).Replace('\','/')
        if ($rel.StartsWith('school-dist/portable-0.1.15-4b/licenses/')) {
            $rel = 'licenses/' + $rel.Substring('school-dist/portable-0.1.15-4b/licenses/'.Length)
        }
        $files.Add($rel)
    }
}
foreach ($rel in $files | Sort-Object -Unique) {
    if ($rel -match '(?i)(\.env|\.pfx|\.pem|\.key|\.exe|\.dll|\.pdf|\.hwp|\.wav|\.mp4|\.log)$' -or
        $rel -match '(?i)(credentials|real.samples|private|secret)') { throw "Refused source path: $rel" }
    $sourceRel = if ($rel.StartsWith('licenses/') -and !$licensesInRepo) {
        'school-dist/portable-0.1.15-4b/' + $rel
    } else { $rel }
    $source = Join-Path $root $sourceRel
    if (!(Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing source: $sourceRel" }
    $dest = Join-Path $out $rel
    New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $dest
}
$count = @(Get-ChildItem -LiteralPath $out -File -Recurse).Count
Write-Host "Source snapshot: $out ($count files)"
