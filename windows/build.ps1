# Bouwt het Windows-installatieprogramma van SellYourShit.
# Gebruik (op Windows, in PowerShell):  windows\build.ps1
# Nodig: internet, nuget.exe en Inno Setup 6 (ISCC.exe). Op GitHub Actions staan die al klaar.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # maakt Invoke-WebRequest veel sneller

# gvsbuild 2026.8.0 heeft PyGObject-wheels voor Python 3.14. Daarvoor bestaan van alle onderdelen
# Windows-wheels (onder meer onnxruntime voor AlphaMaker); voor Python 3.15 nog niet.
$GtkVersie = "2026.8.0"
$PyReeks   = "3.14"           # officiële Python van NuGet (verplaatsbaar): nieuwste 3.14.x
$ModelUrl  = "https://github.com/plemeri/transparent-background/releases/download/1.2.12/ckpt_base.pth"
$ModelMd5  = "d692e3dd5fa1b9658949d452bebf1cda"
# AlphaMaker licht: IS-Net general (Apache-2.0), zelfde bestand dat AlphaMaker anders zelf downloadt
$IsnetUrl  = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx"
$IsnetSha  = "60920e99c45464f2ba57bee2ad08c919a52bbf852739e96947fbb4358c0d964a"

$root   = (Resolve-Path "$PSScriptRoot\..").Path
$cache  = Join-Path $root "cache"
$distR  = Join-Path $root "dist"
$dist   = Join-Path $distR "SellYourShit"
$versie = (Select-String -Path "$root\marktplaats_suite\__init__.py" -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
Write-Host "== SellYourShit $versie"

function Stap($tekst) { Write-Host "== $tekst" }
function Controleer($wat) { if ($LASTEXITCODE -ne 0) { throw "$wat mislukt (code $LASTEXITCODE)" } }

New-Item -ItemType Directory -Force $cache | Out-Null
if (Test-Path $distR) { Remove-Item -Recurse -Force $distR }
New-Item -ItemType Directory -Force $dist | Out-Null

# ---- 1. GTK3 ----
Stap "GTK3 ($GtkVersie)"
$gtkZip = Join-Path $cache "GTK3_Gvsbuild_${GtkVersie}_x64.zip"
if (-not (Test-Path $gtkZip)) {
    Invoke-WebRequest "https://github.com/wingtk/gvsbuild/releases/download/$GtkVersie/GTK3_Gvsbuild_${GtkVersie}_x64.zip" -OutFile $gtkZip
}
$gv = Join-Path $cache "gtk-$GtkVersie"
if (-not (Test-Path "$gv\bin")) { Expand-Archive $gtkZip -DestinationPath $gv -Force }
$gtk = Join-Path $dist "gtk"
New-Item -ItemType Directory -Force "$gtk\bin", "$gtk\lib", "$gtk\share" | Out-Null
Copy-Item "$gv\bin\*.dll" "$gtk\bin\"
foreach ($exe in "gdk-pixbuf-query-loaders.exe", "glib-compile-schemas.exe", "gspawn-win64-helper.exe",
                 "gspawn-win64-helper-console.exe", "gtk-update-icon-cache.exe", "gdbus.exe") {
    if (Test-Path "$gv\bin\$exe") { Copy-Item "$gv\bin\$exe" "$gtk\bin\" }
}
Copy-Item -Recurse "$gv\lib\girepository-1.0" "$gtk\lib\"
Copy-Item -Recurse "$gv\lib\gdk-pixbuf-2.0" "$gtk\lib\"
Copy-Item -Recurse "$gv\share\glib-2.0" "$gtk\share\"
Copy-Item -Recurse "$gv\share\icons" "$gtk\share\"
foreach ($map in "themes", "fontconfig") { if (Test-Path "$gv\share\$map") { Copy-Item -Recurse "$gv\share\$map" "$gtk\share\" } }
if (Test-Path "$gv\etc") { Copy-Item -Recurse "$gv\etc" "$gtk\" }
if (Test-Path "$gv\share\locale\nl") {
    New-Item -ItemType Directory -Force "$gtk\share\locale" | Out-Null
    Copy-Item -Recurse "$gv\share\locale\nl" "$gtk\share\locale\"
}
& "$gtk\bin\glib-compile-schemas.exe" "$gtk\share\glib-2.0\schemas"; Controleer "glib-compile-schemas"
if (Test-Path "$gtk\bin\gtk-update-icon-cache.exe") {
    foreach ($thema in Get-ChildItem "$gtk\share\icons" -Directory) {
        & "$gtk\bin\gtk-update-icon-cache.exe" -q -f -t $thema.FullName
    }
}

# ---- 2. Python ----
$PyVersie = (Invoke-RestMethod "https://api.nuget.org/v3-flatcontainer/python/index.json").versions |
    Where-Object { $_ -match ("^" + [regex]::Escape($PyReeks) + "\.\d+$") } |
    Sort-Object { [version]$_ } | Select-Object -Last 1
if (-not $PyVersie) { throw "geen Python $PyReeks op NuGet gevonden" }
Stap "Python $PyVersie (NuGet)"
$nugetMap = Join-Path $cache "nuget-$PyVersie"
if (-not (Test-Path "$nugetMap\python\tools\python.exe")) {
    nuget install python -Version $PyVersie -OutputDirectory $nugetMap -ExcludeVersion -NonInteractive; Controleer "nuget"
}
Copy-Item -Recurse "$nugetMap\python\tools" "$dist\python"
$py = Join-Path $dist "python\python.exe"
& $py -m pip --version 2>$null
if ($LASTEXITCODE -ne 0) { & $py -m ensurepip --upgrade; Controleer "ensurepip" }
& $py -m pip install --disable-pip-version-check --no-warn-script-location -q --upgrade pip; Controleer "pip upgrade"

# ---- 3. PyGObject en pycairo uit de GTK-bundel ----
Stap "PyGObject en pycairo"
$wheels = Get-ChildItem "$gv\wheels\*.whl" | ForEach-Object { $_.FullName }
& $py -m pip install --disable-pip-version-check --no-warn-script-location -q --no-deps $wheels; Controleer "PyGObject"

# ---- 4. De app met al haar onderdelen ----
Stap "SellYourShit en onderdelen (met achtergrond weghalen op de processor)"
& $py -m pip install --disable-pip-version-check --no-warn-script-location -q --prefer-binary "$root[ai]" pywin32
Controleer "pakketten installeren"

$sp = Join-Path $dist "python\Lib\site-packages"
& $py "$root\windows\zonder_vs16.py" "$sp\marktplaats_suite"; Controleer "emoji-variantkiezers"
& $py -m compileall -q -f "$sp\marktplaats_suite"; Controleer "compileall"

# ---- 5. Opruimen: alleen nodig om zelf C++-uitbreidingen te bouwen ----
Stap "Opruimen"
foreach ($weg in "torch\include", "torch\share\cmake", "torch\test", "caffe2") {
    if (Test-Path "$sp\$weg") { Remove-Item -Recurse -Force "$sp\$weg" }
}
Get-ChildItem "$sp\torch\lib\*.lib" -ErrorAction SilentlyContinue | Remove-Item -Force
foreach ($weg in "linux", "macos") {     # selenium-manager voor andere besturingssystemen
    if (Test-Path "$sp\selenium\webdriver\common\$weg") { Remove-Item -Recurse -Force "$sp\selenium\webdriver\common\$weg" }
}

# ---- 6. Model voor het weghalen van de achtergrond (anders downloadt de app het de eerste keer) ----
Stap "Model transparent-background"
$model = Join-Path $cache "ckpt_base.pth"
if (-not (Test-Path $model) -or (Get-FileHash $model -Algorithm MD5).Hash -ne $ModelMd5.ToUpper()) {
    Invoke-WebRequest $ModelUrl -OutFile $model
    if ((Get-FileHash $model -Algorithm MD5).Hash -ne $ModelMd5.ToUpper()) { throw "model beschadigd (md5)" }
}
New-Item -ItemType Directory -Force "$dist\modellen" | Out-Null
Copy-Item $model "$dist\modellen\"

Stap "Model AlphaMaker licht (IS-Net)"
$isnet = Join-Path $cache "isnet-general.onnx"
if (-not (Test-Path $isnet) -or (Get-FileHash $isnet -Algorithm SHA256).Hash -ne $IsnetSha.ToUpper()) {
    Invoke-WebRequest $IsnetUrl -OutFile $isnet
    if ((Get-FileHash $isnet -Algorithm SHA256).Hash -ne $IsnetSha.ToUpper()) { throw "IS-Net-model beschadigd (sha256)" }
}
New-Item -ItemType Directory -Force "$dist\modellen\alphamaker" | Out-Null
Copy-Item $isnet "$dist\modellen\alphamaker\isnet-general.onnx"

# ---- 7. Starter en pictogram ----
Stap "Starter en pictogram"
Copy-Item "$root\windows\start_sellyourshit.pyw" $dist
& $py -c "from PIL import Image; Image.open(r'$root\marktplaats_suite\assets\icon.png').save(r'$dist\sellyourshit.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
Controleer "pictogram"

$mb = [math]::Round((Get-ChildItem $dist -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)
Stap "Grootte programmamap: $mb MB; grootste onderdelen:"
$grootte = @{}
foreach ($m in (Get-ChildItem $sp -Directory) + (Get-ChildItem $dist -Directory)) {
    $grootte[$m.FullName.Substring($dist.Length + 1)] = (Get-ChildItem $m.FullName -Recurse -File | Measure-Object Length -Sum).Sum
}
$grootte.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 15 |
    ForEach-Object { Write-Host ("   {0,6} MB  {1}" -f [math]::Round($_.Value / 1MB), $_.Key) }

# ---- 8. Installatieprogramma ----
Stap "Installatieprogramma (Inno Setup)"
$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
& $iscc /Q "/DAppVersion=$versie" "/DBronMap=$dist" "/DUitvoer=$distR" "$root\windows\sellyourshit.iss"; Controleer "Inno Setup"
Get-ChildItem "$distR\*.exe" | ForEach-Object { Stap ("Klaar: " + $_.Name + " (" + [math]::Round($_.Length / 1MB) + " MB)") }
