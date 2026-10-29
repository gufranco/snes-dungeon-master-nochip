$ErrorActionPreference = 'Stop'

$project = 'snes-dungeon-master-nochip'
$origin = "https://github.com/gufranco/$project.git"
$root = $PSScriptRoot

function Stop-With([string[]] $lines) {
    foreach ($line in $lines) { [Console]::Error.WriteLine($line) }
    exit 1
}

if (-not (Test-Path (Join-Path $root '.git'))) {
    Stop-With @(
        'This folder has no git metadata, so it came from a downloaded archive.',
        'A downloaded ZIP never carries the submodules and nothing can add them afterwards.',
        'Delete this folder and clone instead:',
        "  git clone --recurse-submodules $origin"
    )
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Stop-With @(
        'Docker is not installed, and every command here runs in its container.',
        'Install Docker Desktop, then open a new terminal.'
    )
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Stop-With @(
        'Docker is installed but its engine is not answering.',
        'Start Docker Desktop and wait until it says the engine is running.'
    )
}

$target = 'runtime'
$command = @('python3') + $args
if ($args.Count -gt 0 -and $args[0] -eq '--gates') {
    $target = 'gates'
    $command = @('sh', 'scripts/gates.sh')
    if ($args.Count -gt 1) {
        $command = @('python3') + @($args | Select-Object -Skip 1)
    }
}
elseif ($args.Count -gt 0 -and $args[0] -eq '--exec') {
    $command = @($args | Select-Object -Skip 1)
}

$image = "${project}:$target"
docker build --quiet --target $target --tag $image $root | Out-Null
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$terminal = @()
if (-not [Console]::IsInputRedirected -and -not [Console]::IsOutputRedirected) {
    $terminal = @('--tty')
}

docker run --rm --interactive @terminal `
    --network none `
    --volume "${root}:/work" `
    --workdir /work `
    $image @command
exit $LASTEXITCODE
