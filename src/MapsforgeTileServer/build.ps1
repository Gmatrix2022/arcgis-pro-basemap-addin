# Build MapsforgeTileServer.jar using local javac
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$outDir = Join-Path $scriptDir "out"
if (Test-Path $outDir) { Remove-Item -Recurse -Force $outDir }
New-Item -ItemType Directory -Path $outDir -Force | Out-Null

$libCp = (Get-ChildItem -Path (Join-Path $scriptDir "lib\*.jar") | ForEach-Object { $_.FullName }) -join ";"
$srcFile = Join-Path $scriptDir "org\mapsforge\map\layer\renderer\MapsforgeTileServer.java"

Write-Host "Compiling MapsforgeTileServer.java..." -ForegroundColor Cyan
& javac -encoding UTF-8 -cp $libCp -d $outDir $srcFile
if ($LASTEXITCODE -ne 0) {
    Write-Error "javac compilation failed!"
    exit 1
}

# Create META-INF/MANIFEST.MF
$metaDir = Join-Path $outDir "META-INF"
New-Item -ItemType Directory -Path $metaDir -Force | Out-Null
$manifest = @"
Manifest-Version: 1.0
Main-Class: org.mapsforge.map.layer.renderer.MapsforgeTileServer
Class-Path: lib/mapsforge-core-0.25.0.jar lib/mapsforge-map-0.25.0.jar lib/mapsforge-map-awt-0.25.0.jar lib/mapsforge-map-reader-0.25.0.jar lib/mapsforge-themes-0.25.0.jar lib/svgSalamander-1.1.3.jar lib/kxml2-2.3.0.jar

"@
[IO.File]::WriteAllText((Join-Path $metaDir "MANIFEST.MF"), $manifest, [System.Text.Encoding]::ASCII)

$jarOut = Join-Path $scriptDir "MapsforgeTileServer.jar"
if (Test-Path $jarOut) { Remove-Item -Force $jarOut }

# Locate jar.exe or fallback to zip archive
$jarExe = (Get-Command jar -ErrorAction SilentlyContinue).Source
if (-not $jarExe) {
    $javacCmd = Get-Command javac -ErrorAction SilentlyContinue
    if ($javacCmd) {
        $cand = Join-Path (Split-Path -Parent $javacCmd.Source) "jar.exe"
        if (Test-Path $cand) { $jarExe = $cand }
    }
}

if ($jarExe -and (Test-Path $jarExe)) {
    & $jarExe cfm $jarOut (Join-Path $metaDir "MANIFEST.MF") -C $outDir .
} else {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory($outDir, $jarOut)
}

Remove-Item -Recurse -Force $outDir
Write-Host "Successfully built: $jarOut" -ForegroundColor Green
