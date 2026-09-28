param(
    [string]$Source = (Join-Path $PSScriptRoot '../school-dist/portable-0.1.15-4b'),
    [string]$MakeAppx = 'C:/Program Files (x86)/Windows Kits/10/bin/10.0.26100.0/x64/makeappx.exe'
)
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$sourceRoot = (Resolve-Path -LiteralPath $Source).Path
$identity = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'store-identity.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($identity.name -ne 'B7EF95FB.5744628220674' -or $identity.displayName -ne '교원호봉획정도우미X슬교행') { throw 'Review the app-specific Partner Center identity before changing this package.' }
if ($identity.version -notmatch '^[1-9]\d*\.\d+\.\d+\.0$') { throw 'Store version must be nonzero-major, four parts, with fourth part 0.' }
if (!(Test-Path -LiteralPath $MakeAppx)) { throw 'Windows SDK MakeAppx not found.' }
$output = Join-Path $repoRoot ('school-dist/store-' + $identity.version + '-4b')
if (Test-Path -LiteralPath $output) { throw "Output already exists; preserve it and use a new version: $output" }
$stage = Join-Path $output 'package'
$unpacked = Join-Path $output 'unpacked'
New-Item -ItemType Directory -Path $stage -Force | Out-Null
# Explicit production files only. Never recursively package the repository.
foreach ($file in @('hobong-desktop.exe','certocr-sidecar.exe','THIRD-PARTY-NOTICES.md')) {
    Copy-Item -LiteralPath (Join-Path $sourceRoot $file) -Destination $stage
}
foreach ($dir in @('runtime','model-cache','licenses')) {
    Copy-Item -LiteralPath (Join-Path $sourceRoot $dir) -Destination $stage -Recurse
}
$assets = Join-Path $stage 'Assets'
New-Item -ItemType Directory -Path $assets | Out-Null
foreach ($icon in @('StoreLogo.png','Square44x44Logo.png','Square150x150Logo.png')) {
    Copy-Item -LiteralPath (Join-Path $repoRoot "desktop/src-tauri/icons/$icon") -Destination $assets
}
$files = @(Get-ChildItem -LiteralPath $stage -Recurse -File)
foreach ($file in $files) {
    $relative = $file.FullName.Substring($stage.Length + 1)
    if ($relative -match '[^\x20-\x7e]' -or $relative -match '(?i)(\.env|\.pfx|\.pem|\.key|\.pdf|\.hwp|\.wav|\.mp4|\.log)$|cuda_v|rocm_|vulkan|__pycache__') {
        throw "Nonproduction or non-ASCII package path: $relative"
    }
}
$escape = { param($s) [Security.SecurityElement]::Escape([string]$s) }
$name = & $escape $identity.name
$publisher = & $escape $identity.publisher
$display = & $escape $identity.displayName
$publisherDisplay = & $escape $identity.publisherDisplayName
$version = $identity.version
$manifest = @"
<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
 xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
 xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
 IgnorableNamespaces="uap rescap">
 <Identity Name="$name" Publisher="$publisher" Version="$version" ProcessorArchitecture="x64" />
 <Properties><DisplayName>$display</DisplayName><PublisherDisplayName>$publisherDisplay</PublisherDisplayName><Logo>Assets\StoreLogo.png</Logo><Description>증명서 읽기, 경력 검토, 호봉획정표 작성을 지원하는 로컬 CPU 앱</Description></Properties>
 <Resources><Resource Language="ko-KR" /></Resources>
 <Dependencies><TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.19041.0" MaxVersionTested="10.0.26200.0" /></Dependencies>
 <Applications><Application Id="App" Executable="hobong-desktop.exe" EntryPoint="Windows.FullTrustApplication">
  <uap:VisualElements DisplayName="$display" Description="교원 호봉획정 업무를 지원합니다."
   BackgroundColor="transparent" Square150x150Logo="Assets\Square150x150Logo.png" Square44x44Logo="Assets\Square44x44Logo.png" />
 </Application></Applications>
 <Capabilities><rescap:Capability Name="runFullTrust" /></Capabilities>
</Package>
"@
[IO.File]::WriteAllText((Join-Path $stage 'AppxManifest.xml'), $manifest, [Text.UTF8Encoding]::new($false))
$package = Join-Path $output ("Hobong_4B_$($identity.version)_x64_unsigned.msix")
# Parallel MakeAppx may reserve half of physical RAM. Serialize files so a
# large model can be packaged while unrelated user workloads keep running.
& $MakeAppx pack /d $stage /p $package /h SHA256 /np *> (Join-Path $output 'makeappx-pack.log')
if ($LASTEXITCODE -ne 0) { throw 'MakeAppx validation/pack failed.' }
& $MakeAppx unpack /p $package /d $unpacked *> (Join-Path $output 'makeappx-unpack.log')
if ($LASTEXITCODE -ne 0) { throw 'MakeAppx unpack failed.' }
$verified = foreach ($file in Get-ChildItem -LiteralPath $stage -File -Recurse) {
    $relative = $file.FullName.Substring($stage.Length + 1)
    $actual = Join-Path $unpacked $relative
    $sha = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    if (!(Test-Path -LiteralPath $actual) -or (Get-FileHash -LiteralPath $actual -Algorithm SHA256).Hash -ne $sha) {
        throw "Unpacked file differs: $relative"
    }
    [ordered]@{path=$relative; bytes=$file.Length; sha256=$sha}
}
$readManifest = [xml](Get-Content -LiteralPath (Join-Path $unpacked 'AppxManifest.xml') -Raw -Encoding UTF8)
if ($readManifest.Package.Identity.Name -ne $identity.name -or $readManifest.Package.Identity.Publisher -ne $identity.publisher) { throw 'Unpacked identity mismatch.' }
$result = [ordered]@{generatedUtc=[DateTime]::UtcNow.ToString('o'); identity=$identity; package=$package;
    bytes=(Get-Item -LiteralPath $package).Length; sha256=(Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash;
    makeappxValidation=$true; parallelCompression=$false; files=$verified; signed=$false; installed=$false; wack=$false; submitted=$false;
    releaseGate='Review release report: licensing, Store listing and certification remain separate from package verification.'}
[IO.File]::WriteAllText((Join-Path $output 'verification.json'), ($result | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
[pscustomobject]$result | Select-Object package,bytes,sha256,makeappxValidation,signed,installed,wack,submitted | Format-List
